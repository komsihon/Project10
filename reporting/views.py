# -*- coding: utf-8 -*-
import json
import os
import shutil
import subprocess
import traceback
import logging
import zipfile
from datetime import datetime
from threading import Thread

from django.conf import settings
from django.contrib.auth.decorators import permission_required
from django.db.models import Sum, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import slugify
from django.views.generic import TemplateView

from ikwen.core.utils import set_counters, calculate_watch_info, slice_watch_objects, rank_watch_objects, \
    get_service_instance
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen_foulassi.foulassi.models import get_school_year, Invoice, Student, Event, EventType, REPORT_CARDS_GENERATED, \
    REPORT_CARDS_FAILED_TO_GENERATE
from ikwen_foulassi.school.models import DisciplineItem, Session, SessionGroup, Classroom, Level, Score
from ikwen_foulassi.reporting.models import DisciplineReport, StudentDisciplineReport, SessionReport, \
    SessionGroupReport, LessonReport, ReportCardBatch
from ikwen_foulassi.reporting.utils import generate_session_report_card, REPORT_CARDS_FOLDER, \
    generate_session_group_report_card, SUMMARY_FOLDER

logger = logging.getLogger('ikwen')


class Dashboard(TemplateView):
    template_name = 'reporting/main.html'

    def get_context_data(self, **kwargs):
        context = super(Dashboard, self).get_context_data(**kwargs)
        discipline_report = []
        school_year = get_school_year(self.request)
        for item in DisciplineItem.objects.filter(is_active=True):
            discipline_report_obj, update = DisciplineReport.objects\
                .get_or_create(discipline_item=item, level=None, classroom=None, school_year=school_year)
            set_counters(discipline_report_obj)
            students_yesterday = slice_watch_objects(StudentDisciplineReport, 1, 'last_add_on')
            students_last_week = slice_watch_objects(StudentDisciplineReport, 7, 'last_add_on')
            students_last_28_days = slice_watch_objects(StudentDisciplineReport, 28, 'last_add_on')
            item_report_obj = {
                'item': item,
                'report': {
                    'yesterday': {
                        'summary': calculate_watch_info(discipline_report_obj.total_history, 1),
                        'student_list': rank_watch_objects(students_yesterday, 'count_history')
                    },
                    'last_week': {
                        'summary': calculate_watch_info(discipline_report_obj.total_history, 7),
                        'student_list': rank_watch_objects(students_last_week, 'count_history')
                    },
                    'last_28_days': {
                        'summary': calculate_watch_info(discipline_report_obj.total_history, 28),
                        'student_list': rank_watch_objects(students_last_28_days, 'count_history')
                    }
                }
            }
            discipline_report.append(item_report_obj)

        # Classes report
        classes_report = {
            'today': {'count': 0, 'hours': 0},
            'yesterday': {'count': 0, 'hours': 0},
            'last_week': {'count': 0, 'hours': 0},
            'last_28_days': {'count': 0, 'hours': 0}
        }
        for report in LessonReport.objects.filter(school_year=school_year):
            classes_report['today']['count'] += calculate_watch_info(report.count_history)['total']
            classes_report['today']['hours'] += calculate_watch_info(report.hours_count_history)['total']

        for report in LessonReport.objects.filter(school_year=school_year):
            classes_report['yesterday']['count'] += calculate_watch_info(report.count_history, 1)['total']
            classes_report['yesterday']['hours'] += calculate_watch_info(report.hours_count_history, 1)['total']

        for report in LessonReport.objects.filter(school_year=school_year):
            classes_report['last_week']['count'] += calculate_watch_info(report.count_history, 7)['total']
            classes_report['last_week']['hours'] += calculate_watch_info(report.hours_count_history, 7)['total']

        for report in LessonReport.objects.filter(school_year=school_year):
            classes_report['last_28_days']['count'] += calculate_watch_info(report.count_history, 28)['total']
            classes_report['last_28_days']['hours'] += calculate_watch_info(report.hours_count_history, 28)['total']

        classroom_count = Classroom.objects.filter(school_year=school_year).count()
        for val in classes_report.values():
            val['count'] = round(float(val['count'])/classroom_count, 2)
            val['hours'] = round(float(val['hours'])/classroom_count, 2)

        # Session scores report
        session_queryset = Session.objects.filter(Q(is_active=False) | Q(is_current=True), school_year=school_year)
        all_session_list = []
        for session in session_queryset:
            if Score.objects.filter(session=session).count() > 0:
                all_session_list.append(session)
        session_group_list = list(SessionGroup.objects.filter(school_year=school_year))
        session_group_count = 0
        if len(all_session_list) >= 2:
            if len(session_group_list) >= 1:
                all_session_list.insert(2, session_group_list[0])
                session_group_count += 1
        if len(all_session_list) >= 5:
            if len(session_group_list) >= 2:
                all_session_list.insert(5, session_group_list[1])
                session_group_count += 1
        if len(all_session_list) >= 8:
            if len(session_group_list) >= 3:
                all_session_list.append(session_group_list[2])
                session_group_count += 1

        session_report, update = SessionReport.objects\
            .get_or_create(level=None, classroom=None, subject=None, school_year=school_year)
        session_group_report, update = SessionGroupReport.objects\
            .get_or_create(level=None, classroom=None, subject=None, school_year=school_year)

        # Billing report
        pending_invoice_count = Invoice.objects.filter(status=Invoice.PENDING, school_year=school_year).count()
        try:
            aggr = Invoice.objects.filter(status=Invoice.PENDING, school_year=school_year).aggregate(Sum('amount'))
            pending_invoice_amount = aggr['amount__sum']
        except IndexError:
            pending_invoice_amount = 0
        pending_invoice_data_list = []
        for classroom in Classroom.objects.filter(school_year=school_year):
            student_list = list(classroom.student_set.filter(is_excluded=False))
            count = Invoice.objects.filter(student__in=student_list, status=Invoice.PENDING).count()
            if count > 0:
                obj = {
                    'classroom': classroom,
                    'count': Invoice.objects.filter(student__in=student_list, status=Invoice.PENDING).count()
                }
                pending_invoice_data_list.append(obj)
        pending_invoice_data_list.sort(cmp=lambda x, y: 1 if x['count'] < y['count'] else -1)
        pending_invoice_data = {
            'count': pending_invoice_count,
            'amount': pending_invoice_amount,
            'list': pending_invoice_data_list
        }
        context['discipline_report'] = discipline_report
        context['all_session_list'] = all_session_list
        context['selected_session'] = all_session_list[-1]
        context['selected_session_order_number'] = all_session_list[-1].order_number
        context['session_report'] = session_report
        context['session_group_report'] = session_group_report
        context['classes_report'] = classes_report
        context['range_session_group'] = range(session_group_count)
        context['range_session'] = range(session_queryset.count())
        context['pending_invoice_data'] = pending_invoice_data
        return context


class DisciplineDetail(TemplateView):
    template_name = 'reporting/discipline_detail.html'


class ReportCardDownloadList(TemplateView):
    template_name = 'reporting/report_card_download_list.html'

    def get_context_data(self, **kwargs):
        context = super(ReportCardDownloadList, self).get_context_data(**kwargs)
        session_id = kwargs['session_id']
        session = get_object_or_404(Session, pk=session_id)
        school_year = get_school_year(self.request)
        report_cards_root = getattr(settings, 'REPORT_CARDS_ROOT')
        report_cards_url = getattr(settings, 'REPORT_CARDS_URL')
        session_group_folder = report_cards_root + '%s_%d-%d/%s/' % (REPORT_CARDS_FOLDER, school_year, school_year + 1,
                                                                     slugify(session.session_group.name).capitalize())
        session_folder = session_group_folder + slugify(session.name).capitalize()
        summary_folder = session_group_folder + SUMMARY_FOLDER
        classroom_list = []
        for classroom in Classroom.objects.filter(school_year=school_year):
            try:
                if session.order_number % 2 == 0:
                    filename = session_folder + '/' + slugify(str(classroom).decode('utf8')) + '.7z'
                    classroom.archive = {
                        'url': filename.replace(report_cards_root, report_cards_url),
                        'size': os.path.getsize(filename) / 1048576.0
                    }
                else:  # Term end
                    summary_filename = summary_folder + '/' + slugify(str(classroom).decode('utf8')) + '.7z'
                    classroom.archive = {
                        'url': summary_filename.replace(report_cards_root, report_cards_url),
                        'size': os.path.getsize(summary_filename) / 1048576.0
                    }
            except OSError:
                continue
            classroom_list.append(classroom)
        if session.order_number % 2 == 0:
            bundle_filename = session_folder + '.7z'
            bundle_archive = {
                'url': bundle_filename.replace(report_cards_root, report_cards_url),
                'size': os.path.getsize(bundle_filename) / 1073741824.0   # Calculate size rather in GB
            }
            context['bundle_archive'] = bundle_archive
        else:
            summary_bundle_filename = summary_folder + '.7z'
            summary_bundle_archive = {
                'url': summary_bundle_filename.replace(report_cards_root, report_cards_url),
                'size': os.path.getsize(summary_bundle_filename) / 1073741824.0
            }
            context['bundle_archive'] = summary_bundle_archive
        context['classroom_list'] = classroom_list
        context['session'] = session
        return context


@permission_required('reporting.ik_manage_reporting')
def generate_report_cards(request, *args, **kwargs):
    if getattr(settings, 'DEBUG', False):
        generate_report_card_files(request)
    else:
        Thread(target=generate_report_card_files, args=(request, )).start()

    event_id = request.GET['event_id']
    Event.objects.filter(pk=event_id).update(is_processed=True)
    response = {'success': True}
    return HttpResponse(json.dumps(response))


def get_report_card_generation_progress(request, *args, **kwargs):
    try:
        batch = ReportCardBatch.objects.all().order_by('-id')[0]
    except IndexError:
        response = {'progress': 100}
    else:
        progress = float(batch.generated) / batch.total
        progress = round(progress, 2)
        response = {'progress': progress}
    return HttpResponse(json.dumps(response))


def generate_report_card_files(request):
    member = request.user
    school_year = get_school_year(request)
    session = Session.get_current()
    is_term_end = session.order_number % 2 != 0
    is_end_year = session.order_number == 5
    total = Student.objects.filter(school_year=school_year, is_excluded=False).count()
    if is_term_end:
        session_group_batch = ReportCardBatch.objects.create(member=member, session_group=session.session_group, total=total)
    else:
        batch = ReportCardBatch.objects.create(member=member, session=session, total=total)
    t0 = datetime.now()
    try:
        EventType.objects.get(codename=REPORT_CARDS_GENERATED)
    except EventType.DoesNotExist:
        EventType.objects.create(codename=REPORT_CARDS_GENERATED,
                                 renderer='ikwen_foulassi.foulassi.events.render_report_cards_generated')
    try:
        EventType.objects.get(codename=REPORT_CARDS_FAILED_TO_GENERATE)
    except EventType.DoesNotExist:
        EventType.objects.create(codename=REPORT_CARDS_FAILED_TO_GENERATE,
                                 renderer='ikwen_foulassi.foulassi.events.render_report_cards_failed_to_generate')

    report_cards_root = getattr(settings, 'REPORT_CARDS_ROOT')
    session_group_folder = report_cards_root + '%s_%d-%d/%s' % (REPORT_CARDS_FOLDER, school_year, school_year + 1,
                                                                slugify(session.session_group.name).capitalize())
    session_folder = session_group_folder + '/' + slugify(session.name).capitalize()
    summary_folder = session_group_folder + '/' + SUMMARY_FOLDER
    session_archive = session_folder + '.7z'
    if is_term_end:
        summary_archive = summary_folder + '.7z'
        if os.path.exists(summary_archive):
            os.unlink(summary_archive)
    else:
        if os.path.exists(session_archive):
            os.unlink(session_archive)
    try:
        for classroom in Classroom.objects.filter(school_year=school_year):
            if classroom.student_set.filter(is_excluded=False).count == 0:
                continue
            if is_term_end:
                generate_session_group_report_card(classroom, session.session_group, session_group_batch)
                classroom_folder = summary_folder + '/' + slugify(str(classroom).decode('utf8'))
                classroom_archive = classroom_folder + '.7z'
                if os.path.exists(classroom_archive):
                    os.unlink(classroom_archive)
                subprocess.call(["7z", "a", classroom_archive, classroom_folder + '/*'])
                subprocess.call(["7z", "a", "-x!*.7z", summary_archive, summary_folder + '/*'])
                subprocess.call(["rm", "-fr", classroom_folder])
            else:
                generate_session_report_card(classroom, session, batch)
                classroom_folder = session_folder + '/' + slugify(str(classroom).decode('utf8'))
                classroom_archive = classroom_folder + '.7z'
                if os.path.exists(classroom_archive):
                    os.unlink(classroom_archive)
                subprocess.call(["7z", "a", classroom_archive, classroom_folder + '/*'])
                subprocess.call(["7z", "a", "-x!*.7z", session_archive, session_folder + '/*'])
                subprocess.call(["rm", "-fr", classroom_folder])

        diff = datetime.now() - t0
        if is_term_end:
            session_group_batch.duration = diff.total_seconds()
            session_group_batch.message = "OK"
        else:
            batch.duration = diff.total_seconds()
            batch.message = "OK"

        event_type = EventType.objects.get(codename=REPORT_CARDS_GENERATED)
        session.report_cards_generated = True
        session.save()
    except:
        service = get_service_instance()
        logger.error("%s: Report cards failed to generate." % service.ikwen_name, exc_info=True)
        if is_term_end:
            session_group_batch.message = traceback.format_exc()
        else:
            batch.message = traceback.format_exc()
        event_type = EventType.objects.get(codename=REPORT_CARDS_FAILED_TO_GENERATE)
    finally:
        if is_term_end:
            session_group_batch.save()
        else:
            batch.save()
        Event.objects.create(type=event_type, object_id_list=[session.id])
