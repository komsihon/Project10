import csv
import json
import logging
import re
import traceback
from datetime import datetime
from copy import copy
from threading import Thread
from time import strptime

from ajaxuploader.views import AjaxFileUploader
from django.conf import settings
from django.contrib import messages
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.core.validators import validate_email
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.template.defaultfilters import slugify
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _, activate
from django.views.decorators.csrf import csrf_protect, csrf_exempt

from ikwen.billing.models import InvoiceItem, InvoiceEntry
from ikwen.billing.utils import get_next_invoice_number
from ikwen.core.constants import MALE, FEMALE
from ikwen.core.utils import get_model_admin_instance, increment_history_field, DefaultUploadBackend, \
    get_service_instance, get_mail_content, send_push
from ikwen.core.templatetags.url_utils import strip_base_alias
from ikwen.core.models import Service
from ikwen.core.views import HybridListView, ChangeObjectBase
from ikwen.accesscontrol.backends import UMBRELLA

from ikwen_foulassi.foulassi.models import Student, Teacher, Invoice, get_school_year, Parent
from ikwen_foulassi.foulassi.utils import remove_student_from_parent_profile, set_student_counts, check_all_scores_set, \
    send_push_to_parents, send_billed_sms
from ikwen_foulassi.reporting.utils import set_counters, calculate_session_report, \
    calculate_session_group_report, set_stats, set_daily_counters_many
from ikwen_foulassi.foulassi.admin import StudentResource
from ikwen_foulassi.reporting.models import SessionReport, LessonReport
from ikwen_foulassi.school.admin import ClassroomAdmin, AssignmentAdmin
from ikwen_foulassi.school.models import Level, Classroom, Session, get_subject_list, Subject, Score, \
    ScoreUpdateRequest, SubjectCoefficient, Lesson, Assignment
from ikwen_foulassi.school.student.views import set_student_invoices
from import_export.formats.base_formats import XLS

logger = logging.getLogger('ikwen')


def import_students(filename, classroom=None, dry_run=True, set_invoices=False):
    abs_path = getattr(settings, 'MEDIA_ROOT') + filename
    fh = open(abs_path, 'r')
    line = fh.readline()
    fh.close()
    data = line.split(',')
    delimiter = ',' if len(data) > 2 else ';'
    error = None
    row_length = 7
    row_length2 = 11  # Student info plus information of one parent. Parent info take 4 columns
    row_length3 = 15  # Student info plus information of two parent
    with open(abs_path) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=delimiter)
        i = -1
        for row in csv_reader:
            i += 1
            if i == 0:
                continue
            if len(row) < row_length or row_length + 1 <= len(row) < row_length2 or row_length2 + 1 <= len(row) < row_length3:
                if len(row) > row_length2:
                    expected = row_length3
                elif len(row) > row_length:
                    expected = row_length2
                else:
                    expected = row_length
                error = _("Missing information at line %(line)d. %(found)d tokens found, "
                          "but %(expected)d expected." % {'line': i + 1, 'found': len(row), 'expected': expected})
                break
            reg_num = row[0].strip()
            if not reg_num:
                error = _("Missing registration number on line %d" % (i + 1))
                break
            last_name = row[1].strip()
            if not last_name:
                error = _("Missing last name on line %d" % (i + 1))
                break
            first_name = row[2].strip()
            if not first_name:
                error = _("Missing first name on line %d" % (i + 1))
                break
            try:
                last_name.decode('utf8')
                first_name.decode('utf8')
            except:
                error = _("Unreadable student name on line %d. Please replace or remove all suspect "
                          "whitespaces and special characters in cells to avoid malicious symbols." % (i + 1))
                break

            gender = row[3].strip()
            if gender.lower().startswith("m"):
                gender = MALE
            elif gender.lower().startswith("f"):
                gender = FEMALE
            else:
                error = _("Unknown gender <strong>%(gender)s</strong> on line %(line)s. "
                          "Must be either <b>Male</b> or <b>Female</b>" % {'gender': gender, 'line': i + 1})
                break
            dob = row[4].strip()
            try:
                st = strptime(dob.replace(' ', '').replace('/', '-'), '%Y-%m-%d')
                dob = datetime(st.tm_year, st.tm_mon, st.tm_mday).date()
            except:
                try:
                    st = strptime(dob.replace(' ', '').replace('/', '-'), '%d-%m-%Y')
                    dob = datetime(st.tm_year, st.tm_mon, st.tm_mday).date()
                except:
                    error = _("Incorrect date of birth <strong>%(dob)s</strong> on line %(line)d. "
                              "Must be in the format <b>Year-Month-Day</b>" % {'dob': dob, 'line': i + 1})
                    break
            is_repeating = row[5].strip()
            if is_repeating.capitalize() not in ("Yes", "Y", "No", "N", "Oui", "O", "Non"):
                error = _("Incorrect Repetition <strong>%(rep)s</strong> on line %(line)d. "
                          "Must be either <b>Yes</b> or <b>No</b>" % {'rep': is_repeating, 'line': i + 1})
                break
            is_repeating = True if is_repeating in ("Yes", "Y", "Oui", "O") else False
            year_joined = row[6].strip()
            try:
                year_joined = int(year_joined)
            except ValueError:
                error = _("Year joined <strong>%(year_joined)s</strong> on line %(line)d is incorrect. "
                          "Please check." % {'year_joined': year_joined, 'line': i + 1})
                break
            year = get_school_year()
            if year_joined > year:
                error = _("Year joined <strong>%(year_joined)s</strong> on line %(line)d seems incorrect. "
                          "Please check." % {'year_joined': year_joined, 'line': i + 1})
                break

            parent1_name, parent1_relationship, parent1_email, parent1_phone = None, None, None, None
            parent2_name, parent2_relationship, parent2_email, parent2_phone = None, None, None, None

            parent1_is_set = row[7] or row[8] or row[9] or row[10]
            if parent1_is_set:  # Information for one parent were set
                parent1_name = row[7].strip()
                try:
                    parent1_name.decode('utf8')
                except:
                    error = _("Unreadable Parent 1 name on line %d. Please replace or remove all suspect "
                              "whitespaces and special characters to avoid malicious symbols." % (i + 1))
                    break
                parent1_relationship = row[8].strip()
                if not parent1_relationship:
                    error = _("Missing parent 1 relationship on line %d. Use one of "
                              "<strong>Father</strong>, <strong>Mother</strong>, <strong>Uncle</strong>, etc" % (i + 1))
                    break
                try:
                    parent1_relationship = parent1_relationship.decode('utf8')
                except:
                    error = _("Unreadable parent 1 relationship on line %d. Please replace or remove all suspect "
                              "whitespaces and special characters to avoid malicious symbols." % (i + 1))
                    break
                parent1_email = row[9].strip()
                if parent1_email:
                    try:
                        validate_email(parent1_email)
                    except ValidationError:
                        error = _("Incorrect parent 1 email <strong>%(email)s</strong> on "
                                  "line %(line)d" % {'email': parent1_email, 'line': (i + 1)})
                        break
                parent1_phone = row[10]
                if not re.match('\d{9}', slugify(parent1_phone).replace('-', '')):
                    error = _("Missing or incorrect parent 1 phone <strong>%(phone)s</strong> on line %(line)d. "
                              "Phone must be composed of 9 digits." % {'phone': parent1_phone, 'line': (i + 1)})
                    break

            parent2_is_set = row[11] or row[12] or row[13] or row[14]  # Information for second parent were set
            if parent2_is_set:
                parent2_name = row[11].strip()
                try:
                    parent2_name.decode('utf8')
                except:
                    error = _("Unreadable Parent 2 name on line %d. Please replace or remove all suspect "
                              "whitespaces and special characters to avoid malicious symbols." % (i + 1))
                    break
                if (parent1_name and parent2_name) and parent2_name == parent1_name:
                    error = _("1st and 2nd parent have the same name <strong>%(name)s</strong> "
                              "on line %(line)d. Please change." % {'name': parent2_name, 'line': (i + 1)})
                    break
                parent2_relationship = row[12].strip()
                if not parent2_relationship:
                    error = _("2nd parent parent relationship missing on line %d. Use one of "
                              "<strong>Father</strong>, <strong>Mother</strong>, <strong>Uncle</strong>, etc" % (i + 1))
                    break
                if parent2_relationship == parent1_relationship:
                    error = _("1st and 2nd parent have the same relationship <strong>%(relation)s</strong> "
                              "on line %(line)d. Please change." % {'relation': parent2_relationship, 'line': (i + 1)})
                    break
                try:
                    parent2_relationship = parent2_relationship.decode('utf8')
                except:
                    error = _("Unreadable parent 2 relationship on line %d. Please replace or remove all suspect"
                              "whitespaces and special characters to avoid malicious symbols." % (i + 1))
                    break
                parent2_email = row[13].strip()
                if parent2_email:
                    try:
                        validate_email(parent2_email)
                    except ValidationError:
                        error = _("2nd parent email <strong>%(email)s</strong> incorrect on "
                                  "line %(line)d" % {'email': parent2_email, 'line': (i + 1)})
                        break
                    if parent2_email == parent1_email:
                        error = _("1st and 2nd parent have the same email <strong>%(email)s</strong> on line %(line)d. "
                                  "Please change." % {'email': parent2_email, 'line': (i + 1)})
                        break
                parent2_phone = row[14]
                if parent2_phone:
                    if not re.match('\d{9}', slugify(parent2_phone).replace('-', '')):
                        error = _("2nd parent phone <strong>%(phone)s</strong> missing or incorrect on line %(line)d. "
                                  "Phone must be composed of 9 digits." % {'phone': parent2_phone, 'line': (i + 1)})
                        break
                if parent2_phone == parent1_phone:
                    error = _("1st and 2nd parent have the same phone <strong>%(phone)s</strong> on line %(line)d. "
                              "Please change." % {'phone': parent2_phone, 'line': (i + 1)})
                    break
            if not dry_run:
                try:
                    Student.objects.get(registration_number=reg_num)
                except Student.DoesNotExist:
                    try:
                        tags = slugify(last_name + ' ' + first_name).replace('-', ' ')
                        student = Student.objects\
                            .create(classroom=classroom, registration_number=reg_num, first_name=first_name,
                                    last_name=last_name, gender=gender, dob=dob, is_repeating=is_repeating,
                                    year_joined=year_joined, tags=tags)
                        student_u = Student.objects.using(UMBRELLA)\
                            .create(id=student.id, classroom=classroom, registration_number=reg_num,
                                    first_name=first_name, last_name=last_name, gender=gender, dob=dob,
                                    is_repeating=is_repeating, year_joined=year_joined, tags=tags)
                        if parent1_is_set:
                            parent1_phone = slugify(parent1_phone).replace('-', '')
                            parent1 = Parent.objects.create(student=student, name=parent1_name, phone=parent1_phone,
                                                            email=parent1_email, relation=parent1_relationship)
                            Parent.objects.using(UMBRELLA)\
                                .create(id=parent1.id, student=student_u, name=parent1_name, phone=parent1_phone,
                                        email=parent1_email, relation=parent1_relationship)
                        if parent2_is_set:
                            parent2_phone = slugify(parent2_phone).replace('-', '')
                            parent2 = Parent.objects.create(student=student, name=parent2_name, phone=parent2_phone,
                                                            email=parent2_email, relation=parent2_relationship)
                            Parent.objects.using(UMBRELLA)\
                                .create(id=parent2.id, student=student_u, name=parent2_name, phone=parent2_phone,
                                        email=parent2_email, relation=parent2_relationship)
                        if set_invoices:
                            set_student_invoices(student)
                    except:
                        if getattr(settings, 'DEBUG', False):
                            error = traceback.format_exc()
                        else:
                            error = "Unknow server error. Please try again later"
                        break
    return error


def notify_parents_for_new_invoice(classroom, label, amount):
    try:
        foulassi = Service.objects.using(UMBRELLA).get(project_name_slug='foulassi')
    except:
        foulassi = None
    weblet = get_service_instance()
    config = weblet.config
    queryset = Student.objects.filter(classroom=classroom, is_excluded=False)
    for student in queryset:
        body = _("We are kindly informing you that a new payment of %(amount)s is expected for %(invoice_title)s "
                 "of %(student)s." % {'amount': intcomma(amount), 'invoice_title': label, 'student': student})
        target = reverse('foulassi:kid_detail', args=(weblet.ikwen_name, student.id))
        target = strip_base_alias(target).replace('/foulassi', '')

        parents = student.parent_set.select_related('member').all()
        for parent in parents:
            try:
                member = parent.member
                if member:
                    activate(member.language)
                    send_push(foulassi, member, config.company_name, body, target)
            except:
                logger.error("%s - Error in notifications" % weblet.project_name_slug, exc_info=True)
                continue


class StudentUploadBackend(DefaultUploadBackend):

    def upload_complete(self, request, filename, *args, **kwargs):
        path = self.UPLOAD_DIR + "/" + filename
        self._dest.close()
        try:
            error = import_students(path)
        except Exception as e:
            error = e.message
        return {
            'path': getattr(settings, 'MEDIA_URL') + path,
            'error_message': error
        }


upload_student_file = AjaxFileUploader(StudentUploadBackend)


class ClassroomList(HybridListView):
    model = Classroom
    template_name = 'school/classroom/classroom_list.html'

    def get_context_data(self, **kwargs):
        context = super(ClassroomList, self).get_context_data(**kwargs)
        level_classroom_list = []
        member = self.request.user
        school_year = get_school_year(self.request)
        if self.request.session.get('is_teacher'):
            teacher = Teacher.objects.get(member=member, school_year=school_year)
            level_classroom_list = [{
                "name": _("All your classrooms"),
                "classroom_list": sorted(teacher.get_classroom_list())
            }]
        else:
            for level in Level.objects.filter(school_year=school_year).order_by('order_of_appearance', 'name'):
                obj = {
                    "name": level.name,
                    "boys_count": level.boys_count,
                    "girls_count": level.girls_count,
                    "student_count": level.student_count,
                    "classroom_list": Classroom.objects.filter(level=level)
                }
                level_classroom_list.append(obj)
        context['level_classroom_list'] = level_classroom_list
        context['level_list'] = Level.objects.all()
        return context


class ChangeClassroom(ChangeObjectBase):
    template_name = 'school/classroom/change_classroom.html'
    model = Classroom
    model_admin = ClassroomAdmin

    def get_model_form(self, obj):
        form = super(ChangeClassroom, self).get_model_form(obj)
        school_year = get_school_year(self.request)
        form.fields['level'].queryset = Level.objects.filter(school_year=school_year)
        form.fields['professor'].queryset = Teacher.objects.filter(school_year=school_year)
        return form

    def get_context_data(self, **kwargs):
        context = super(ChangeClassroom, self).get_context_data(**kwargs)
        classroom = context[self.context_object_name]
        classroom_subject_list = []
        if classroom:
            classroom_subject_list = get_subject_list(classroom)
            if not classroom_subject_list:
                classroom_subject_list = get_subject_list(classroom.level)
        subject_list = []
        for subject in Subject.objects.filter(is_visible=True):
            try:
                index = classroom_subject_list.index(subject)
                subject.is_active = True
                subject.group = classroom_subject_list[index].group
                subject.coefficient = classroom_subject_list[index].coefficient
                subject.lessons_due = classroom_subject_list[index].lessons_due
                subject.hours_due = classroom_subject_list[index].hours_due
                subject.teacher = classroom_subject_list[index].get_teacher(classroom)
            except:
                pass
            subject_list.append(subject)
        context['subject_list'] = subject_list
        level_info = {}
        for level in Level.objects.all():
            obj = {
                'registration_fees': level.registration_fees,
                'first_instalment': level.first_instalment,
                'second_instalment': level.second_instalment,
                'third_instalment': level.third_instalment,
                'subject_list': [{'id': subject.id, 'group': subject.group, 'coefficient': subject.coefficient,
                                  'lessons_due': subject.lessons_due, 'hours_due': subject.hours_due}
                                 for subject in get_subject_list(level)]
            }
            level_info[level.id] = obj
        context['level_info'] = json.dumps(level_info)
        context['teacher_list'] = Teacher.objects.filter(school_year=get_school_year(self.request))
        context['range_1_4'] = range(1, 4)
        return context

    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        object_id = kwargs.get('object_id')
        if object_id:
            obj = get_object_or_404(self.model, pk=object_id)
        else:
            obj = self.model()
        object_admin = get_model_admin_instance(self.model, self.model_admin)
        ModelForm = object_admin.get_form(request)
        form = ModelForm(request.POST, instance=obj)
        if form.is_valid():
            obj.level = form.cleaned_data['level']
            obj.name = form.cleaned_data['name']
            obj.slug = slugify(obj.level) + '-' + slugify(obj.name)
            obj.registration_fees = form.cleaned_data['registration_fees']
            obj.first_instalment = form.cleaned_data['first_instalment']
            obj.second_instalment = form.cleaned_data['second_instalment']
            obj.third_instalment = form.cleaned_data['third_instalment']
            subject_coefficient_list = []
            subjects = request.POST['subjects'].strip()
            if subjects:
                for item in subjects.split(','):
                    try:
                        tk = item.split(':')
                        subject = Subject.objects.get(pk=tk[0])
                        subject_coefficient = SubjectCoefficient(subject=subject, group=int(tk[1]), coefficient=int(tk[2]),
                                                                 lessons_due=int(tk[3]), hours_due=int(tk[4]))
                        subject_coefficient_list.append(subject_coefficient)
                    except:
                        continue
                    try:
                        teacher = Teacher.objects.get(pk=tk[5])
                        subject.set_teacher(obj, teacher)
                    except:
                        pass
            obj.subject_coefficient_list = subject_coefficient_list
            obj.save()
            next_url = self.get_object_list_url(request, obj)
            if object_id:
                notice = u'%s <strong>%s</strong> %s' % (obj._meta.verbose_name.capitalize(), unicode(obj), _('successfully updated'))
            else:
                notice = u'%s <strong>%s</strong> %s' % (obj._meta.verbose_name.capitalize(), unicode(obj), _('successfully changed'))
            messages.success(request, notice)
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)


class ClassroomDetail(ChangeObjectBase):
    template_name = 'school/classroom/classroom_detail.html'
    model = Classroom
    model_admin = ClassroomAdmin
    context_object_name = 'classroom'

    def get_context_data(self, **kwargs):
        context = super(ClassroomDetail, self).get_context_data(**kwargs)
        classroom = context['classroom']
        member = self.request.user
        school_year = get_school_year(self.request)
        student_list = classroom.student_set.filter(is_excluded=False).order_by('last_name')
        if member.has_perm('school.ik_access_scores'):
            try:
                teacher = Teacher.objects.get(member=member, school_year=school_year)
                subject_list = list(teacher.get_subject_list(classroom))
            except Teacher.DoesNotExist:
                subject_list = get_subject_list(classroom)
            tab_count = len(subject_list)
            context['subject_list'] = subject_list
            for student in student_list:
                student.scores = []
                for subject in subject_list:
                    student.scores.append(student.get_score_list(subject))
        else:
            tab_count = 1
            context['tabs_hidden'] = True
        context['range_tab_count'] = range(tab_count)
        context['student_list'] = student_list
        return context

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super(ClassroomDetail, self).dispatch(request, *args, **kwargs)

    def mark(self, request, classroom):
        # def cmp_scores_dict(x, y):
        #     if x['score'] == y['score']:
        #         return 0
        #     return 1 if x['score'] > y['score'] else -1
        now = datetime.now()
        data = json.loads(request.body)
        subject_id = data['subject_id']
        subject = Subject.objects.get(pk=subject_id)
        school_year = get_school_year()
        session = Session.get_current()
        if not session:
            response = {'error': _("No session created. Create sessions first.")}
            return HttpResponse(json.dumps(response))
        elif not (session.is_current and session.is_active):
            response = {'error': _("Cannot mark on a terminated session.")}
            return HttpResponse(json.dumps(response))
        level = classroom.level
        score_list = data['scores']
        try:
            foulassi = Service.objects.using(UMBRELLA).get(project_name_slug='foulassi')
        except:
            foulassi = None
        # score_list.sort(cmp=cmp_scores_dict, reverse=True)
        update_list = []
        classroom_stats, change = SessionReport.objects.get_or_create(level=level, classroom=classroom, subject=subject, school_year=school_year)
        level_stats, is_level_update = SessionReport.objects.get_or_create(level=level, classroom=None, subject=subject, school_year=school_year)
        boys_participation, boys_total_scores, boys_success = 0, 0, 0
        girls_participation, girls_total_scores, girls_success = 0, 0, 0
        boys_highest_score, boys_lowest_score = Score(value=0), Score(value=20)
        girls_highest_score, girls_lowest_score = Score(value=0), Score(value=20)
        i = session.order_number
        set_counters(classroom_stats, i)
        set_counters(level_stats, i)
        level_stats.boys_highest_score_history[i] = Score(value=0)
        level_stats.girls_highest_score_history[i] = Score(value=0)
        level_stats.boys_lowest_score_history[i] = Score(value=20)
        level_stats.girls_lowest_score_history[i] = Score(value=20)
        for item in score_list:
            student_id = item['student_id']
            value = float(item['score'])
            try:
                student = Student.objects.get(pk=student_id)
                if student.gender == MALE:
                    boys_participation += 1
                    boys_highest_score = max(boys_highest_score, Score(session=session, subject=subject, student=student, value=value))
                    boys_lowest_score = min(boys_lowest_score, Score(session=session, subject=subject, student=student, value=value))
                    boys_total_scores += value
                    if value >= 10:
                        boys_success += 1
                else:
                    girls_participation += 1
                    girls_highest_score = max(girls_highest_score, Score(session=session, subject=subject, student=student, value=value))
                    girls_lowest_score = min(girls_lowest_score, Score(session=session, subject=subject, student=student, value=value))
                    girls_total_scores += value
                    if value >= 10:
                        girls_success += 1
                try:
                    score = Score.objects.get(session=session, subject=subject, student=student)
                    if score.value != value:
                        diff = now - score.updated_on
                        score.value = value
                        score.save()
                        Student.objects.filter(pk=student.id).update(has_new=True)
                        Student.objects.using(UMBRELLA).filter(pk=student.id).update(has_new=True)
                        if diff.total_seconds() >= 86400:  # Suspicious score update after 24 hours
                            score_update = Score(session=session, subject=subject, student=student, value=value)
                            update_list.append(score_update)
                except Score.DoesNotExist:
                    Score.objects.create(session=session, subject=subject, student=student, value=value)
                    Student.objects.filter(pk=student.id).update(has_new=True)
                    Student.objects.using(UMBRELLA).filter(pk=student.id).update(has_new=True)
                    parents = student.parent_set.select_related('member').all()
                    text = _("Your kid %(student)s scored %(score)s in %(subject)s for the last "
                             "evaluation." % {'student': student, 'score': value, 'subject': subject})
                    weblet = get_service_instance()
                    config = weblet.config
                    uri = reverse('foulassi:kid_detail', args=(weblet.ikwen_name, student_id, ))
                    target = 'https://foulassi.ikwen.com' + strip_base_alias(uri).replace('/foulassi', '') + '?tab=scores'
                    Thread(target=send_push_to_parents, args=(foulassi, config.company_name, parents, text, target)).start()
                    if request.GET.get('send_sms'):
                        Thread(target=send_billed_sms, args=(weblet, parents, text)).start()
            except Student.DoesNotExist:
                pass

        if getattr(settings, 'DEBUG', False):
            set_stats(classroom_stats, level_stats, None, session, boys_participation, boys_highest_score,
                      boys_lowest_score, boys_total_scores, boys_success, girls_participation, girls_highest_score,
                      girls_lowest_score, girls_total_scores, girls_success)
        else:
            Thread(target=set_stats,
                   args=(classroom_stats, level_stats, None, session, boys_participation, boys_highest_score,
                         boys_lowest_score, boys_total_scores, boys_success, girls_participation, girls_highest_score,
                         girls_lowest_score, girls_total_scores, girls_success)).start()

        Thread(target=check_all_scores_set, args=(session, )).start()

        if update_list:
            ScoreUpdateRequest.objects.create(session=session, subject=subject, classroom=classroom,
                                              member=self.request.user, update_list=update_list)

        if getattr(settings, 'DEBUG', False):
            calculate_session_report(session, classroom)
        else:
            Thread(target=calculate_session_report, args=(session, classroom)).start()
        if (session.order_number + 1) % 2 == 0:
            session_group = session.session_group
            if getattr(settings, 'DEBUG', False):
                calculate_session_group_report(session_group, classroom)
            else:
                Thread(target=calculate_session_group_report, args=(session_group, classroom)).start()
        response = {'success': True}
        return HttpResponse(json.dumps(response))

    def import_student_file(self, context):
        classroom = context['classroom']
        media_url = getattr(settings, 'MEDIA_URL')
        filename = self.request.GET['filename'].replace(media_url, '')
        set_invoices = self.request.GET.get('set_invoices')
        error = import_students(filename)
        if error:
            return HttpResponse(json.dumps({'error': error}))
        import_students(filename, classroom, dry_run=False, set_invoices=set_invoices)
        Thread(target=set_student_counts).start()
        context['student_list'] = classroom.student_set.filter(is_excluded=False)
        return render(self.request, 'school/snippets/classroom/student_list.html', context)

    def get_export_filename(self, classroom, file_format):
        date_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = "%s_%s.%s" % (classroom, date_str, file_format.get_extension())
        return filename

    def export_student_file(self, classroom):
        file_format = XLS()
        queryset = classroom.student_set.filter(is_excluded=False)
        data = StudentResource().export(queryset)
        export_data = file_format.export_data(data)
        content_type = file_format.get_content_type()
        try:
            response = HttpResponse(export_data, content_type=content_type)
        except TypeError:
            response = HttpResponse(export_data, mimetype=content_type)
        response['Content-Disposition'] = 'attachment; filename=%s' % self.get_export_filename(classroom, file_format)
        return response

    def render_to_response(self, context, **response_kwargs):
        action = self.request.GET.get('action')
        classroom = context['classroom']
        if action == 'import_student_file':
            return self.import_student_file(context)
        if action == 'export':
            return self.export_student_file(classroom)
        if action == 'set_leader':
            return self.set_leader(classroom)
        elif action == 'add_lesson':
            return self.add_lesson(classroom)
        elif action == 'add_invoice':
            return self.add_invoice(context)
        elif action == 'generate_report_cards':
            from ikwen_foulassi.reporting.models import ReportCardHeader
            from ikwen_foulassi.reporting.views import generate_report_card_files
            if not classroom.mark_students:
                response = {"error": _("Report card cannot be generated for classroom where students are not marked.")}
                return HttpResponse(json.dumps(response), 'content-type: text/json')
            lang = self.request.GET['lang']
            lang_name = self.request.GET['lang_name']
            try:
                ReportCardHeader.objects.get(lang=lang)
            except ReportCardHeader.DoesNotExist:
                response = {"error": _("Report card header not configured for %s" % lang_name),
                            "tip": _("Please configure report card header for %s " % lang_name),
                            "url": reverse("reporting:change_reportcardheader") + "?lang=" + lang}
                return HttpResponse(json.dumps(response), 'content-type: text/json')
            if getattr(settings, 'DEBUG', False):
                generate_report_card_files(self.request, classroom)
            else:
                Thread(target=generate_report_card_files, args=(self.request, classroom)).start()
            return HttpResponse(json.dumps({"success": True}), 'content-type: text/json')
        elif action == 'delete':
            selection = self.request.GET['selection'].strip(',').split(',')
            deleted = []
            for pk in selection:
                try:
                    student = Student.objects.get(pk=pk)
                    if student.is_confirmed:
                        message = _("Cannot delete a confirmed student: %s. Exclude instead, "
                                    "only the head of school can do that." % student)
                        break
                    student_copy = copy(student)
                    student.delete()
                    Student.objects.using(UMBRELLA).filter(pk=pk).delete()
                    for parent in student_copy.parent_set.all():
                        Thread(target=remove_student_from_parent_profile,
                               args=(student_copy, parent.email, parent.phone)).start()
                        parent.delete()
                    deleted.append(pk)
                except:
                    continue
            else:
                message = _("%d item(s) deleted." % len(selection))
            Thread(target=set_student_counts).start()
            response = {
                'message': message,
                'deleted': deleted
            }
            return HttpResponse(json.dumps(response), 'content-type: text/json')
        return super(ClassroomDetail, self).render_to_response(context, **response_kwargs)

    def set_leader(self, classroom):
        student_id = self.request.GET['student_id']
        student = get_object_or_404(Student, pk=student_id)
        classroom.leader = student
        classroom.save()
        response = {'success': True,
                    'leader_name': str(student),
                    'message': _("Class leader correctly set to %s" % str(student))}
        return HttpResponse(json.dumps(response))

    def add_lesson(self, classroom):
        level = classroom.level
        member = self.request.user
        school_year = get_school_year(self.request)
        subject_id = self.request.GET['subject_id']
        title = self.request.GET['title']
        hours_count = int(self.request.GET['hours_count'])
        is_complete = True if self.request.GET['is_complete'] else False
        subject = get_object_or_404(Subject, pk=subject_id)
        teacher = Teacher.objects.get(member=member, school_year=school_year)
        Lesson.objects.create(classroom=classroom, subject=subject, teacher=teacher,
                              title=title, hours_count=hours_count, is_complete=is_complete)
        classroom_report, update = LessonReport.objects.get_or_create(subject=subject, level=level, classroom=classroom)
        level_report, update = LessonReport.objects.get_or_create(subject=None, level=level, classroom=None)
        school_report, update = LessonReport.objects.get_or_create(subject=None, level=None, classroom=None)
        set_daily_counters_many(classroom_report, level_report, school_report)
        increment_history_field(classroom_report, 'hours_count_history', hours_count)
        increment_history_field(level_report, 'hours_count_history', hours_count)
        increment_history_field(school_report, 'hours_count_history', hours_count)
        if is_complete:
            increment_history_field(classroom_report, 'count_history')
            increment_history_field(level_report, 'count_history')
            increment_history_field(school_report, 'count_history')
        response = {'success': True,
                    'message': _("Lesson successfully added.")}
        return HttpResponse(json.dumps(response))

    def add_invoice(self, context):
        classroom = context['classroom']
        label = self.request.GET['label']
        amount = float(self.request.GET['amount'])
        due_date = self.request.GET['due_date']
        failed = []
        queryset = Student.objects.filter(classroom=classroom, is_excluded=False)
        for student in queryset:
            try:
                item = InvoiceItem(label=label, amount=amount)
                entries = [InvoiceEntry(item, total=amount)]
                number = get_next_invoice_number()
                Invoice.objects.create(number=number, student=student, entries=entries,  amount=amount,
                                       due_date=due_date, last_reminder=datetime.now())
            except:
                failed.append(student)
        count = queryset.count()
        if len(failed) == 0:
            response = {'success': True}
        elif len(failed) < count:
            response = {'failed': [student.to_dict() for student in queryset]}
        elif len(failed) == count:
            response = {'failed': "Could not place invoices. Contact administrator"}
        Thread(target=notify_parents_for_new_invoice, args=(classroom, label, amount)).start()
        return HttpResponse(json.dumps(response))

    def post(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'mark':
            classroom = Classroom.objects.get(pk=kwargs['object_id'])
            return self.mark(request, classroom)


class AssignmentList(HybridListView):
    model = Assignment
    search_field = 'subject'
    list_filter = (
        ('subject', _('Subjects')),
        ('deadline', _('Deadlines'))
    )
    template_name = 'school/classroom/assignment_list.html'
    html_results_template_name = 'school/snippets/classroom/assignment_list_results.html'

    def get_queryset(self, **kwargs):
        classroom_id = self.request.GET['classroom_id']
        school_year = get_school_year(self.request)
        try:
            classroom = get_object_or_404(Classroom, pk=classroom_id)
            teacher = Teacher.objects.get(member=self.request.user, school_year=school_year)
            subject_list = list(teacher.get_subject_list(classroom))
        except Teacher.DoesNotExist:
            subject_list = []
        queryset = Assignment.objects.filter(classroom=classroom_id, subject__in=subject_list)
        return queryset

    def get_change_object_url(self, request, **kwargs):
        classroom_id = self.request.GET['classroom_id']
        return reverse('school:change_assignment', args=(classroom_id, ))

    def get_context_data(self, **kwargs):
        context = super(AssignmentList, self).get_context_data(**kwargs)
        classroom_id = self.request.GET['classroom_id']
        context['classroom_id'] = classroom_id
        context['classroom'] = Classroom.objects.get(pk=classroom_id)
        context['classroom_list'] = Classroom.objects.all()
        return context


class ChangeAssignment(ChangeObjectBase):
    model = Assignment
    model_admin = AssignmentAdmin
    template_name = 'school/classroom/change_assignment.html'
    label_field = 'title'

    def get_object_list_url(self, request, obj, *args, **kwargs):
        classroom_id = kwargs['classroom_id']
        return reverse('school:assignment_list') + '?classroom_id=' + classroom_id

    def get_context_data(self, **kwargs):
        context = super(ChangeAssignment, self).get_context_data(**kwargs)
        classroom = Classroom.objects.get(pk=kwargs['classroom_id'])
        assignment = context['obj']
        context['classroom'] = classroom
        school_year = get_school_year(self.request)
        try:
            teacher = Teacher.objects.get(member=self.request.user, school_year=school_year)
            subject_list = list(teacher.get_subject_list(classroom))
            context['authorized_teacher'] = True if not assignment else assignment.subject in subject_list
        except Teacher.DoesNotExist:
            subject_list = get_subject_list(classroom)
        context['subject_list'] = subject_list
        context['classroom_list'] = Classroom.objects.all()
        return context

    def after_save(self, request, obj, *args, **kwargs):
        """
        Run after the form is successfully saved
        in the post() function
        """
        try:
            foulassi = Service.objects.using(UMBRELLA).get(project_name_slug='foulassi')
        except:
            foulassi = None
        service = get_service_instance()
        school_config = service.config
        classroom = Classroom.objects.get(pk=kwargs['classroom_id'])
        # for student in Student.objects.filter(classroom=classroom, kid_fees_paid=True):
        for student in Student.objects.filter(classroom=classroom):
            for parent in student.parent_set.all():
                try:
                    parent_email = parent.get_email()
                    parent_name = parent.get_name()
                except:
                    continue

                company_name = school_config.company_name
                sender = '%s via ikwen Foulassi <no-reply@ikwen.com>' % company_name

                cta_url = 'https://foulassi.ikwen.com' + reverse('foulassi:change_homework',
                                                                 args=(service.ikwen_name,
                                                                       student.pk, obj.pk))
                if parent.member:
                    activate(parent.member.language)
                subject = _("New assignment in %s" % obj.subject.name)
                extra_context = {'parent_name': parent_name, 'cta_url': cta_url,
                                 'school_name': company_name,
                                 'student_name': student.first_name,
                                 'assignment': obj,
                                 }
                try:
                    html_content = get_mail_content(subject,
                                                    template_name='foulassi/mails/new_assignment.html',
                                                    extra_context=extra_context)
                except:
                    logger.error("Could not generate HTML content from template", exc_info=True)
                    continue

                msg = EmailMessage(subject, html_content, sender,
                                   [parent_email, 'rsihon@gmail.com', 'wilfriedwillend@gmail.com',
                                    'rmbogning@gmail.com', 'silatchomsiaka@gmail.com'])
                msg.content_subtype = "html"
                try:
                    msg.send()
                except Exception as e:
                    logger.debug(e.message)

                body = _('Your child has a new assignment in '
                         '%(subject)s about %(title)s' % {'subject': subject, 'title': obj.title})

                if parent.member:
                    send_push(foulassi, parent.member, subject, body, cta_url)
