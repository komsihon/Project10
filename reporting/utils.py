# -*- coding: utf-8 -*-
import os
from collections import OrderedDict
from datetime import datetime
from xml.sax.saxutils import escape

from django.conf import settings
from django.db.models import Sum
from django.template import Context
from django.template.defaultfilters import slugify
from django.template.loader import get_template
from django.utils.translation import ugettext as _

from trml2pdf import trml2pdf

from ikwen.core.constants import MALE, FEMALE
from ikwen.core.utils import get_service_instance

from ikwen_foulassi.foulassi.models import BEST_OF_ALL, Student
from ikwen_foulassi.school.models import Score, SessionGroupScore, DisciplineItem, Subject, get_subject_list, Classroom, \
    Level, Session
from ikwen_foulassi.reporting.models import SessionReport, SessionGroupReport

from ikwen_foulassi.foulassi.models import get_school_year
from ikwen_foulassi.school.models import DisciplineLogEntry

REPORT_CARDS_FOLDER = "ReportCards"
SUMMARY_FOLDER = "Summary"  # Holds the term summary from 2 sessions


def set_counters(tracker_object, i=0):
    if not tracker_object:
        return
    history_fields = [field for field in tracker_object.__dict__.keys() if field.endswith('_history')]
    for name in history_fields:
        field = tracker_object.__getattribute__(name)
        while len(field) < i + 1:
            field.append(0)


def set_daily_counters(tracker_object):
    if not tracker_object:
        return
    history_fields = [field for field in tracker_object.__dict__.keys() if field.endswith('_history')]
    config = get_service_instance().config
    diff = datetime.now() - config.back_to_school_date
    gap = diff.days + 1
    for name in history_fields:
        field = tracker_object.__getattribute__(name)
        while len(field) < gap:
            field.append(0)


def set_daily_counters_many(*args):
    """
    Call set_daily_counters on multiple WatchObject.
    """
    for tracker_object in args:
        set_daily_counters(tracker_object)


def calculate_session_participation_and_success(session, level_stats, school_stats=None):
    i = session.order_number
    school_year = get_school_year()
    subject = level_stats.subject
    level = level_stats.level
    classroom_list = list(Classroom.objects.filter(level=level))
    boys = list(Student.objects.filter(classroom__in=classroom_list, gender=MALE))
    girls = list(Student.objects.filter(classroom__in=classroom_list, gender=FEMALE))
    if subject:
        boys_participation = Score.objects.filter(session=session, student__in=boys, subject=subject).count()
        girls_participation = Score.objects.filter(session=session, student__in=girls, subject=subject).count()
        boys_success = Score.objects.filter(session=session, student__in=boys, subject=subject, value__gte=10).count()
        girls_success = Score.objects.filter(session=session, student__in=girls, subject=subject, value__gte=10).count()
    else:
        boys_participation = Score.objects.filter(session=session, student__in=boys).count()
        girls_participation = Score.objects.filter(session=session, student__in=girls).count()
        boys_success = Score.objects.filter(session=session, student__in=boys, value__gte=10).count()
        girls_success = Score.objects.filter(session=session, student__in=girls, value__gte=10).count()
    level_stats.boys_participation_history[i] = boys_participation
    level_stats.girls_participation_history[i] = girls_participation
    level_stats.boys_success_history[i] = boys_success
    level_stats.girls_success_history[i] = girls_success
    level_stats.save()

    if school_stats:
        boys_participation, girls_participation, boys_success, girls_success = 0, 0, 0, 0
        for level in Level.objects.filter(school_year=school_year):
            classroom_list = list(Classroom.objects.filter(level=level))
            boys = list(Student.objects.filter(classroom__in=classroom_list, gender=MALE))
            girls = list(Student.objects.filter(classroom__in=classroom_list, gender=FEMALE))
            boys_participation += Score.objects.filter(session=session, subject=None, student__in=boys).count()
            girls_participation += Score.objects.filter(session=session, subject=None, student__in=girls).count()
            boys_success += Score.objects.filter(session=session, subject=None, student__in=boys, value__gte=10).count()
            girls_success += Score.objects.filter(session=session, subject=None, student__in=girls, value__gte=10).count()
        school_stats.boys_participation_history[i] = boys_participation
        school_stats.girls_participation_history[i] = girls_participation
        school_stats.boys_success_history[i] = boys_success
        school_stats.girls_success_history[i] = girls_success
        school_stats.save()


def calculate_session_group_participation_and_success(session_group, level_stats, school_stats=None):
    i = session_group.order_number
    school_year = get_school_year()
    subject = level_stats.subject
    level = level_stats.level
    classroom_list = list(Classroom.objects.filter(level=level))
    boys = list(Student.objects.filter(classroom__in=classroom_list, gender=MALE))
    girls = list(Student.objects.filter(classroom__in=classroom_list, gender=FEMALE))
    if subject:
        boys_participation = SessionGroupScore.objects.filter(session_group=session_group, student__in=boys, subject=subject).count()
        girls_participation = SessionGroupScore.objects.filter(session_group=session_group, student__in=girls, subject=subject).count()
        boys_success = SessionGroupScore.objects.filter(session_group=session_group, student__in=boys, subject=subject, value__gte=10).count()
        girls_success = SessionGroupScore.objects.filter(session_group=session_group, student__in=girls, subject=subject, value__gte=10).count()
    else:
        boys_participation = SessionGroupScore.objects.filter(session_group=session_group, student__in=boys).count()
        girls_participation = SessionGroupScore.objects.filter(session_group=session_group, student__in=girls).count()
        boys_success = SessionGroupScore.objects.filter(session_group=session_group, student__in=boys, value__gte=10).count()
        girls_success = SessionGroupScore.objects.filter(session_group=session_group, student__in=girls, value__gte=10).count()
    level_stats.boys_participation_history[i] = boys_participation
    level_stats.girls_participation_history[i] = girls_participation
    level_stats.boys_success_history[i] = boys_success
    level_stats.girls_success_history[i] = girls_success
    level_stats.save()

    if school_stats:
        boys_participation, girls_participation, boys_success, girls_success = 0, 0, 0, 0
        for level in Level.objects.filter(school_year=school_year):
            classroom_list = list(Classroom.objects.filter(level=level))
            boys = list(Student.objects.filter(classroom__in=classroom_list, gender=MALE))
            girls = list(Student.objects.filter(classroom__in=classroom_list, gender=FEMALE))
            boys_participation += SessionGroupScore.objects.filter(session_group=session_group, subject=None, student__in=boys).count()
            girls_participation += SessionGroupScore.objects.filter(session_group=session_group, subject=None, student__in=girls).count()
            boys_success += SessionGroupScore.objects.filter(session_group=session_group, subject=None, student__in=boys, value__gte=10).count()
            girls_success += SessionGroupScore.objects.filter(session_group=session_group, subject=None, student__in=girls, value__gte=10).count()
        school_stats.boys_participation_history[i] = boys_participation
        school_stats.girls_participation_history[i] = girls_participation
        school_stats.boys_success_history[i] = boys_success
        school_stats.girls_success_history[i] = girls_success
        school_stats.save()


def get_session_group_scores(session_group, subject, student):
    session_list = list(session_group.session_set.all())
    try:
        score1 = Score.objects.get(session=session_list[0], subject=subject, student=student)
    except Score.DoesNotExist:
        score1 = Score.objects.create(session=session_list[0], subject=subject, student=student, value=0)
    try:
        score2 = Score.objects.get(session=session_list[1], subject=subject, student=student)
    except Score.DoesNotExist:
        score2 = Score.objects.create(session=session_list[1], subject=subject, student=student, value=0)
    return score1.value, score2.value


def calculate_session_report(session, classroom, subject_list=None):
    """
    Calculates and sets students average scores
    report for a given session and classroom
    """
    student_list = classroom.student_set.filter(is_excluded=False)
    if not subject_list:
        subject_list = get_subject_list(classroom)
    session_avg_score_list = []
    level = classroom.level

    school_year = get_school_year()
    classroom_stats, change = SessionReport.objects.get_or_create(level=level, classroom=classroom, subject=None, school_year=school_year)
    level_stats, change = SessionReport.objects.get_or_create(level=level, classroom=None, subject=None, school_year=school_year)
    school_stats, change = SessionReport.objects.get_or_create(level=None, classroom=None, subject=None, school_year=school_year)
    boys_participation, boys_total_scores, boys_success = 0, 0, 0
    girls_participation, girls_total_scores, girls_success = 0, 0, 0
    boys_highest_score, boys_lowest_score = Score(value=0), Score(value=20)
    girls_highest_score, girls_lowest_score = Score(value=0), Score(value=20)

    i = session.order_number
    set_counters(classroom_stats, i)
    set_counters(level_stats, i)
    set_counters(school_stats, i)

    level_stats.boys_highest_score_history[i] = Score(value=0)
    level_stats.girls_highest_score_history[i] = Score(value=0)
    level_stats.boys_lowest_score_history[i] = Score(value=20)
    level_stats.girls_lowest_score_history[i] = Score(value=20)

    school_stats.boys_highest_score_history[i] = Score(value=0)
    school_stats.girls_highest_score_history[i] = Score(value=0)
    school_stats.boys_lowest_score_history[i] = Score(value=20)
    school_stats.girls_lowest_score_history[i] = Score(value=20)

    for student in student_list:
        total_score = 0
        total_coefficient = 0
        for subject in subject_list:
            try:
                score = Score.objects.get(session=session, student=student, subject=subject)
                total_score += score.value * subject.coefficient
                total_coefficient += subject.coefficient
            except Score.DoesNotExist:
                continue
        student_avg = round(total_score / total_coefficient, 2)
        avg_score, change = Score.objects.get_or_create(session=session, student=student, subject=None)
        avg_score.value = student_avg
        avg_score.save()
        session_avg_score_list.append(avg_score)

        if student.gender == MALE:
            boys_participation += 1
            boys_highest_score = max(boys_highest_score, avg_score)
            boys_lowest_score = min(boys_lowest_score, avg_score)
            boys_total_scores += student_avg
            if student_avg >= 10:
                boys_success += 1
        else:
            girls_participation += 1
            girls_highest_score = max(girls_highest_score, avg_score)
            girls_lowest_score = min(girls_lowest_score, avg_score)
            girls_total_scores += student_avg
            if student_avg >= 10:
                girls_success += 1

    session_avg_score_list.sort(reverse=True)
    i = 0
    for session_avg_score in session_avg_score_list:
        if i >= 1 and session_avg_score.value == session_avg_score_list[i - 1].value:
            session_avg_score.rank = i  # This helps manage ex-aequo ranks
        else:
            session_avg_score.rank = i + 1
        session_avg_score.save()
        i += 1

    set_stats(classroom_stats, level_stats, school_stats, session,
              boys_participation, boys_highest_score, boys_lowest_score, boys_total_scores, boys_success,
              girls_participation, girls_highest_score, girls_lowest_score, girls_total_scores, girls_success)

    return session_avg_score_list


def calculate_session_group_report(session_group, classroom):
    level = classroom.level
    config = get_service_instance().config
    subject_list = get_subject_list(classroom)
    session_list = list(session_group.session_set.all())
    student_list = classroom.student_set.filter(is_excluded=False)
    avg_score_list = []

    school_year = get_school_year()
    classroom_stats, change = SessionGroupReport.objects.get_or_create(level=level, classroom=classroom, subject=None, school_year=school_year)
    level_stats, change = SessionGroupReport.objects.get_or_create(level=level, classroom=None, subject=None, school_year=school_year)
    school_stats, change = SessionGroupReport.objects.get_or_create(level=None, classroom=None, subject=None, school_year=school_year)
    boys_participation, boys_total_scores, boys_success = 0, 0, 0
    girls_participation, girls_total_scores, girls_success = 0, 0, 0
    boys_highest_score, boys_lowest_score = Score(value=0), Score(value=20)
    girls_highest_score, girls_lowest_score = Score(value=0), Score(value=20)

    i = session_group.order_number
    set_counters(classroom_stats, i)
    set_counters(level_stats, i)
    set_counters(school_stats, i)

    level_stats.boys_highest_score_history[i] = Score(value=0)
    level_stats.girls_highest_score_history[i] = Score(value=0)
    level_stats.boys_lowest_score_history[i] = Score(value=20)
    level_stats.girls_lowest_score_history[i] = Score(value=20)

    school_stats.boys_highest_score_history[i] = Score(value=0)
    school_stats.girls_highest_score_history[i] = Score(value=0)
    school_stats.boys_lowest_score_history[i] = Score(value=20)
    school_stats.girls_lowest_score_history[i] = Score(value=20)

    for student in student_list:
        total_score = 0
        total_coefficient = 0
        for subject in subject_list:
            score_list = []
            for session in session_list:
                try:
                    score = Score.objects.get(session=session, student=student, subject=subject)
                    score_list.append(score.value)
                except Score.DoesNotExist:
                    score_list.append(0)
            if config.session_group_avg == BEST_OF_ALL:
                subject_student_avg = max(score_list)
            else:  # Defaults to AVERAGE_OF_ALL
                subject_student_avg = sum(score_list) / len(score_list)
            subject_sg_score, update = SessionGroupScore.objects.\
                get_or_create(session_group=session_group, student=student, subject=subject)
            subject_sg_score.value1 = score_list[0]
            subject_sg_score.value2 = score_list[1]
            subject_sg_score.value = subject_student_avg
            subject_sg_score.save()
            total_score += subject_student_avg * subject.coefficient
            total_coefficient += subject.coefficient
        student_avg = round(total_score / total_coefficient, 2)
        avg_score, update = SessionGroupScore.objects.get_or_create(session_group=session_group, student=student, subject=None)
        avg_score.value = student_avg
        avg_score_list.append(avg_score)

        if student.gender == MALE:
            boys_participation += 1
            boys_highest_score = max(boys_highest_score, Score(subject=None, student=student, value=student_avg))
            boys_lowest_score = min(boys_lowest_score, Score(subject=None, student=student, value=student_avg))
            boys_total_scores += student_avg
            if student_avg >= 10:
                boys_success += 1
        else:
            girls_participation += 1
            girls_highest_score = max(girls_highest_score, Score(subject=None, student=student, value=student_avg))
            girls_lowest_score = min(girls_lowest_score, Score(subject=None, student=student, value=student_avg))
            girls_total_scores += student_avg
            if student_avg >= 10:
                girls_success += 1

    avg_score_list.sort(reverse=True)
    i = 0
    for score in avg_score_list:
        if i >= 1 and score.value == avg_score_list[i - 1].value:
            score.rank = i  # This helps manage ex-aequo ranks
        else:
            score.rank = i + 1
        score.save()
        i += 1

    set_stats(classroom_stats, level_stats, school_stats, session_group,
              boys_participation, boys_highest_score, boys_lowest_score, boys_total_scores, boys_success,
              girls_participation, girls_highest_score, girls_lowest_score, girls_total_scores, girls_success)

    return avg_score_list


def set_stats(classroom_stats, level_stats, school_stats, session,
              boys_participation, boys_highest_score, boys_lowest_score, boys_total_scores, boys_success,
              girls_participation, girls_highest_score, girls_lowest_score, girls_total_scores, girls_success):
    """
    Set stats after a score input.
    """
    i = session.order_number
    classroom_stats.boys_participation_history[i] = boys_participation
    classroom_stats.boys_highest_score_history[i] = boys_highest_score
    classroom_stats.boys_lowest_score_history[i] = boys_lowest_score
    classroom_boys_avg = float(boys_total_scores) / boys_participation if boys_participation > 0 else 0
    classroom_stats.boys_avg_score_history[i] = round(classroom_boys_avg, 2)
    classroom_stats.boys_success_history[i] = boys_success

    if level_stats.boys_avg_score_history[i] == 0:
        level_boys_total_score = boys_total_scores
        level_boys_total_participation = boys_participation
    else:
        level_boys_total_score = level_stats.boys_avg_score_history[i] * level_stats.boys_participation_history[i]
        level_boys_total_score += boys_total_scores
        level_boys_total_participation = level_stats.boys_participation_history[i] + boys_participation
    level_boys_avg = float(level_boys_total_score) / level_boys_total_participation if level_boys_total_participation > 0 else 0
    level_stats.boys_avg_score_history[i] = round(level_boys_avg, 2)
    level_stats.boys_highest_score_history[i] = max(level_stats.boys_highest_score_history[i], boys_highest_score)
    level_stats.boys_lowest_score_history[i] = min(level_stats.boys_lowest_score_history[i], boys_lowest_score)

    classroom_stats.girls_participation_history[i] = girls_participation
    classroom_stats.girls_highest_score_history[i] = girls_highest_score
    classroom_stats.girls_lowest_score_history[i] = girls_lowest_score
    classroom_girls_avg = float(girls_total_scores) / girls_participation if girls_participation > 0 else 0
    classroom_stats.girls_avg_score_history[i] = round(classroom_girls_avg, 2)
    classroom_stats.girls_success_history[i] = girls_success
    classroom_stats.save()

    if level_stats.girls_avg_score_history[i] == 0:
        level_girls_total_score = girls_total_scores
        level_girls_total_participation = girls_participation
    else:
        level_girls_total_score = level_stats.girls_avg_score_history[i] * level_stats.girls_participation_history[i]
        level_girls_total_score += girls_total_scores
        level_girls_total_participation = level_stats.girls_participation_history[i] + girls_participation
    level_girls_avg = float(level_girls_total_score) / level_girls_total_participation if level_girls_total_participation > 0 else 0
    level_stats.girls_avg_score_history[i] = round(level_girls_avg, 2)
    level_stats.girls_highest_score_history[i] = max(level_stats.girls_highest_score_history[i], girls_highest_score)
    level_stats.girls_lowest_score_history[i] = min(level_stats.girls_lowest_score_history[i], girls_lowest_score)
    level_stats.save()

    if school_stats:
        school_stats.boys_highest_score_history[i] = max(school_stats.boys_highest_score_history[i], boys_highest_score)
        school_stats.boys_lowest_score_history[i] = min(school_stats.boys_lowest_score_history[i], boys_lowest_score)
        school_stats.girls_highest_score_history[i] = max(school_stats.girls_highest_score_history[i], girls_highest_score)
        school_stats.girls_lowest_score_history[i] = min(school_stats.girls_lowest_score_history[i], girls_lowest_score)
        school_stats.save()

    if type(session) == Session:
        calculate_session_participation_and_success(session, level_stats, school_stats)
    else:
        calculate_session_group_participation_and_success(session, level_stats, school_stats)


def generate_session_report_card(classroom, session, report_card_header, batch):
    student_list = classroom.student_set.filter(is_excluded=False)
    if student_list.count() == 0:
        return

    date_generated = datetime.now().strftime('%d/%m/%Y')
    school_year = get_school_year()

    service = get_service_instance()
    config = service.config
    subject_coefficient_list = classroom.subject_coefficient_list
    subject_coefficient_list.sort()
    subject_group_list = [subject.group for subject in subject_coefficient_list]
    subject_group_list = list(set(subject_group_list))  # Removes duplicates
    subject_group_list.sort()

    # Discipline criteria
    try:
        absence = DisciplineItem.objects.get(slug=DisciplineItem.ABSENCE)
    except DisciplineItem.DoesNotExist:
        absence = DisciplineItem.objects.create(name=_("Absence"), slug=DisciplineItem.ABSENCE)
    try:
        lateness = DisciplineItem.objects.get(slug=DisciplineItem.LATENESS)
    except DisciplineItem.DoesNotExist:
        lateness = DisciplineItem.objects.create(name=_("Lateness"), slug=DisciplineItem.LATENESS)
    try:
        warning = DisciplineItem.objects.get(slug=DisciplineItem.WARNING)
    except DisciplineItem.DoesNotExist:
        warning = DisciplineItem.objects.create(name=_("Warning"), slug=DisciplineItem.WARNING)
    try:
        censure = DisciplineItem.objects.get(slug=DisciplineItem.CENSURE)
    except DisciplineItem.DoesNotExist:
        censure = DisciplineItem.objects.create(name=_("Censure"), slug=DisciplineItem.CENSURE)
    try:
        exclusion = DisciplineItem.objects.get(slug=DisciplineItem.EXCLUSION)
    except DisciplineItem.DoesNotExist:
        exclusion = DisciplineItem.objects.create(name=_("Exclusion"), slug=DisciplineItem.EXCLUSION)

    report_cards_root = getattr(settings, 'REPORT_CARDS_ROOT')
    session_folder = report_cards_root + '%s_%d-%d/%s/%s/' % (REPORT_CARDS_FOLDER, school_year, school_year + 1,
                                                              slugify(session.session_group.name).capitalize(),
                                                              slugify(session.name).capitalize())
    classroom_folder = session_folder + slugify(str(classroom).decode('utf8')) + '/'
    if not os.path.exists(classroom_folder):
        os.makedirs(classroom_folder)

    score_matrix = OrderedDict()
    for student in student_list:
        for group in subject_group_list:
            group_name = 'Group%d' % group
            group_total_score = 0.0
            group_total_coefficient = 0
            if not score_matrix.get(group_name):
                score_matrix[group_name] = {'score_list': []}
            for obj in subject_coefficient_list:
                if obj.group != group:
                    continue
                subject = obj.subject
                if not score_matrix.get(subject.slug):
                    score_matrix[subject.slug] = {'score_list': []}
                try:
                    score = Score.objects.get(session=session, student=student, subject=subject)
                except Score.DoesNotExist:
                    score = Score.objects.create(session=session, student=student, subject=subject, value=0)
                group_total_score += score.value * obj.coefficient
                group_total_coefficient += obj.coefficient
                score_matrix[subject.slug]['score_list'].append(score)

            grp_avg_value = round(group_total_score / group_total_coefficient, 2)
            subject_group, update = Subject.objects.get_or_create(name=group_name, slug=slugify(group_name), is_visible=False)
            grp_avg_score, update = Score.objects.get_or_create(session=session, student=student, subject=subject_group)
            grp_avg_score.value = grp_avg_value
            score_matrix[group_name]['score_list'].append({'score': grp_avg_score, 'total_score': group_total_score,
                                                           'total_coef': group_total_coefficient})

    total_coefficient = 0
    for obj in subject_coefficient_list:
        subject = obj.subject
        total_coefficient += obj.coefficient
        score_list = score_matrix[subject.slug]['score_list']
        classroom_avg = 0.0
        for score in score_list:
            classroom_avg += score.value
        classroom_avg /= len(score_list)
        score_matrix[subject.slug]['classroom_avg'] = round(classroom_avg, 2)
        score_matrix[subject.slug]['max'] = max(score_list)
        score_matrix[subject.slug]['min'] = min(score_list)

    for group in subject_group_list:
        group_name = 'Group%d' % group
        score_list = [item['score'] for item in score_matrix[group_name]['score_list']]
        score_list.sort(reverse=True)
        i = 0
        classroom_avg = 0.0
        for score in score_list:
            if i >= 1 and score.value == score_list[i - 1].value:
                score.rank = i  # This helps manage ex-aequo ranks
            else:
                score.rank = i + 1
            score.save()
            classroom_avg += score.value
            i += 1
        classroom_avg /= len(score_list)
        score_matrix[group_name]['classroom_avg'] = round(classroom_avg, 2)

    classroom_total = 0.0
    for student in student_list:
        try:
            session_score = Score.objects.get(session=session, student=student, subject__isnull=True)
        except Score.DoesNotExist:
            session_score = Score.objects.create(session=session, student=student, value=0)
        classroom_total += session_score.value
    classroom_general_avg = round(classroom_total / len(student_list), 2)
    classroom_general_avg_min = Score.objects.filter(session=session, subject__isnull=True).order_by('value')[0]
    classroom_general_avg_max = Score.objects.filter(session=session, subject__isnull=True).order_by('-value')[0]

    student_score_matrix = OrderedDict()
    i = -1
    for student in student_list:
        i += 1
        total_score = 0.0
        for group in subject_group_list:
            group_name = 'Group%d' % group
            group_total_score = score_matrix[group_name]['score_list'][i]['total_score']
            group_total_coef = score_matrix[group_name]['score_list'][i]['total_coef']
            student_score_matrix[group_name] = {
                'total_score': group_total_score,
                'total_coef': group_total_coef,
                'avg_score': score_matrix[group_name]['score_list'][i]['score'],
                'classroom_avg': score_matrix[group_name]['classroom_avg'],
                'subject_list': []
            }
            for obj in subject_coefficient_list:
                if obj.group == group:
                    subject = obj.subject
                    score = score_matrix[subject.slug]['score_list'][i]
                    teacher_name = subject.get_teacher(classroom).member.full_name
                    student_score_matrix[group_name]['subject_list'].append({
                        'teacher_name': escape(teacher_name).encode('ascii', 'xmlcharrefreplace'),
                        'subject_name': escape(subject.name).encode('ascii', 'xmlcharrefreplace'),
                        'coefficient': obj.coefficient,
                        'total_score': obj.coefficient * score.value,
                        'score': score,
                        'max': score_matrix[subject.slug]['max'],
                        'min': score_matrix[subject.slug]['min'],
                        'classroom_avg': score_matrix[subject.slug]['classroom_avg']
                    })
            total_score += group_total_score

        session_score = Score.objects.get(student=student, session=session, subject__isnull=True)

        start, end = session.starts_on, session.ends_on
        absence_count_justified = DisciplineLogEntry.objects\
            .filter(student=student, item=absence, is_justified=True, happened_on__range=(start, end)).count()
        absence_count_non_justified = DisciplineLogEntry.objects\
            .filter(student=student, item=absence, is_justified=False, happened_on__range=(start, end)).count()
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=absence, is_justified=True, happened_on__range=(start, end)).aggregate(Sum('count'))
            absence_duration_justified = aggr['count__sum']
        except IndexError:
            absence_duration_justified = 0
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=absence, is_justified=False, happened_on__range=(start, end)).aggregate(Sum('count'))
            absence_duration_non_justified = aggr['count__sum']
        except IndexError:
            absence_duration_non_justified = 0
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=lateness, is_justified=True, happened_on__range=(start, end)).aggregate(Sum('count'))
            lateness_count_justified = aggr['count__sum']
        except IndexError:
            lateness_count_justified = 0
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=lateness, is_justified=False, happened_on__range=(start, end)).aggregate(Sum('count'))
            lateness_count_non_justified = aggr['count__sum']
        except IndexError:
            lateness_count_non_justified = 0
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=warning, happened_on__range=(start, end)).aggregate(Sum('count'))
            warning_count = aggr['count__sum']
        except IndexError:
            warning_count = 0
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=censure, happened_on__range=(start, end)).aggregate(Sum('count'))
            censure_count = aggr['count__sum']
        except IndexError:
            censure_count = 0
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=exclusion, happened_on__range=(start, end)).aggregate(Sum('count'))
            exclusion_count = aggr['count__sum']
        except IndexError:
            exclusion_count = 0

        from ikwen.conf import settings as ikwen_settings
        media_root = getattr(settings, 'MEDIA_ROOT')
        head_organization_logo = media_root + report_card_header.head_organization_logo.name
        if not os.path.isfile(head_organization_logo):
            head_organization_logo = ''
        school_logo = media_root + config.logo.name
        if not os.path.isfile(school_logo):
            school_logo = ''
        student_photo = ikwen_settings.MEDIA_ROOT + student.photo.name
        if not os.path.isfile(student_photo):
            student_photo = ''

        context = Context({
            # Special Labels
            'label_school_year': _("School year").encode('ascii', 'xmlcharrefreplace'),
            'label_student_name': _("Student name").encode('ascii', 'xmlcharrefreplace'),
            'label_subjects': _("Subjects").encode('ascii', 'xmlcharrefreplace'),
            'label_results': _("Results").encode('ascii', 'xmlcharrefreplace'),
            'label_council_decision': _("Council decision").encode('ascii', 'xmlcharrefreplace'),
            # End special labels

            'ministry_logo': head_organization_logo,
            'school_logo': school_logo,
            'student_photo': student_photo,

            'country_name': escape(report_card_header.country_name).encode('ascii', 'xmlcharrefreplace'),
            'country_motto': escape(report_card_header.country_moto).encode('ascii', 'xmlcharrefreplace'),
            'head_organization': escape(report_card_header.head_organization).encode('ascii', 'xmlcharrefreplace'),
            'sequence_number': escape(session.name).encode('ascii', 'xmlcharrefreplace'),
            'school_address': escape(config.address).encode('ascii', 'xmlcharrefreplace'),
            'school_contact': escape(config.contact_phone).encode('ascii', 'xmlcharrefreplace'),
            'school_name': escape(config.company_name).encode('ascii', 'xmlcharrefreplace'),
            'school_motto': escape(config.slogan).encode('ascii', 'xmlcharrefreplace'),

            'school_year': "%d - %d" % (school_year, school_year + 1),
            'city_name': escape(config.city).encode('ascii', 'xmlcharrefreplace'),
            'classroom': classroom,
            'student': student,
            'first_name': escape(student.first_name).encode('ascii', 'xmlcharrefreplace'),
            'last_name': escape(student.last_name).encode('ascii', 'xmlcharrefreplace'),
            'classroom_name': escape(str(classroom).decode('utf8')).encode('ascii', 'xmlcharrefreplace'),
            'classroom_level_name': escape(str(classroom.level).decode('utf8')).encode('ascii', 'xmlcharrefreplace'),
            'student_score_matrix': student_score_matrix,
            'total_score': total_score,
            'total_coef': total_coefficient,
            'session_score': session_score,
            'classroom_general_avg': classroom_general_avg,
            'classroom_general_avg_min': classroom_general_avg_min,
            'classroom_general_avg_max': classroom_general_avg_max,
            'absence_count_justified': absence_count_justified,
            'absence_duration_justified': absence_duration_justified,
            'absence_count_non_justified': absence_count_non_justified,
            'absence_duration_non_justified': absence_duration_non_justified,
            'lateness_count_justified': lateness_count_justified,
            'lateness_count_non_justified': lateness_count_non_justified,
            'warning_count': warning_count,
            'censure_count': censure_count,
            'exclusion_count': exclusion_count,
            'date_generated': date_generated
        })
        template = get_template('reporting/session_report_card.rml.html')
        xmlstring = template.render(context)
        pdfstr = trml2pdf.parseString(xmlstring)
        report_card = classroom_folder + slugify(str(student).decode('utf8')).capitalize() + '.pdf'
        f = open(report_card, 'w')
        f.write(pdfstr)
        batch.generated += 1
        batch.save()


def generate_session_group_report_card(classroom, session_group, report_card_header, batch):
    student_list = classroom.student_set.filter(is_excluded=False)
    if student_list.count() == 0:
        return

    date_generated = datetime.now().strftime('%d/%m/%Y')
    school_year = get_school_year()

    service = get_service_instance()
    config = service.config
    subject_coefficient_list = classroom.subject_coefficient_list
    subject_coefficient_list.sort()
    subject_group_list = [subject.group for subject in subject_coefficient_list]
    subject_group_list = list(set(subject_group_list))  # Removes duplicates
    subject_group_list.sort()

    # Discipline criteria
    try:
        absence = DisciplineItem.objects.get(slug=DisciplineItem.ABSENCE)
    except DisciplineItem.DoesNotExist:
        absence = DisciplineItem.objects.create(name=_("Absence"), slug=DisciplineItem.ABSENCE)
    try:
        lateness = DisciplineItem.objects.get(slug=DisciplineItem.LATENESS)
    except DisciplineItem.DoesNotExist:
        lateness = DisciplineItem.objects.create(name=_("Lateness"), slug=DisciplineItem.LATENESS)
    try:
        warning = DisciplineItem.objects.get(slug=DisciplineItem.WARNING)
    except DisciplineItem.DoesNotExist:
        warning = DisciplineItem.objects.create(name=_("Warning"), slug=DisciplineItem.WARNING)
    try:
        censure = DisciplineItem.objects.get(slug=DisciplineItem.CENSURE)
    except DisciplineItem.DoesNotExist:
        censure = DisciplineItem.objects.create(name=_("Censure"), slug=DisciplineItem.CENSURE)
    try:
        exclusion = DisciplineItem.objects.get(slug=DisciplineItem.EXCLUSION)
    except DisciplineItem.DoesNotExist:
        exclusion = DisciplineItem.objects.create(name=_("Exclusion"), slug=DisciplineItem.EXCLUSION)

    report_cards_root = getattr(settings, 'REPORT_CARDS_ROOT')
    session_folder = report_cards_root + '%s_%d-%d/%s/%s/' % (REPORT_CARDS_FOLDER, school_year, school_year + 1,
                                                              slugify(session_group.name).capitalize(), SUMMARY_FOLDER)
    classroom_folder = session_folder + slugify(str(classroom).decode('utf8')) + '/'
    if not os.path.exists(classroom_folder):
        os.makedirs(classroom_folder)

    score_matrix = OrderedDict()
    for student in student_list:
        for group in subject_group_list:
            group_name = 'Group%d' % group
            group_total_score = 0.0
            group_total_coefficient = 0
            if not score_matrix.get(group_name):
                score_matrix[group_name] = {'score_list': []}
            for obj in subject_coefficient_list:
                if obj.group != group:
                    continue
                subject = obj.subject
                if not score_matrix.get(subject.slug):
                    score_matrix[subject.slug] = {'score_list': []}
                try:
                    score = SessionGroupScore.objects.get(session_group=session_group, student=student, subject=subject)
                except SessionGroupScore.DoesNotExist:
                    value1, value2 = get_session_group_scores(session_group, student, subject)
                    if config.session_group_avg == BEST_OF_ALL:
                        value = max(value1, value2)
                    else:  # Defaults to AVERAGE_OF_ALL
                        value = (value1 + value2) / 2
                    score = SessionGroupScore.objects.create(session_group=session_group, student=student,
                                                             subject=subject, value1=value1, value2=value2, value=value)

                group_total_score += score.value * obj.coefficient
                group_total_coefficient += obj.coefficient
                score_matrix[subject.slug]['score_list'].append(score)

            grp_avg_value = round(group_total_score / group_total_coefficient, 2)
            subject_group, update = Subject.objects.get_or_create(name=group_name, slug=slugify(group_name), is_visible=False)
            grp_avg_score, update = SessionGroupScore.objects\
                .get_or_create(session_group=session_group, student=student, subject=subject_group)
            grp_avg_score.value = grp_avg_value
            score_matrix[group_name]['score_list'].append({'score': grp_avg_score, 'total_score': group_total_score,
                                                           'total_coef': group_total_coefficient})

    total_coefficient = 0
    for obj in subject_coefficient_list:
        subject = obj.subject
        total_coefficient += obj.coefficient
        score_list = score_matrix[subject.slug]['score_list']
        classroom_avg = 0.0
        for score in score_list:
            classroom_avg += score.value
        classroom_avg /= len(score_list)
        score_matrix[subject.slug]['classroom_avg'] = round(classroom_avg, 2)
        score_matrix[subject.slug]['max'] = max(score_list)
        score_matrix[subject.slug]['min'] = min(score_list)

    for group in subject_group_list:
        group_name = 'Group%d' % group
        score_list = [item['score'] for item in score_matrix[group_name]['score_list']]
        score_list.sort(reverse=True)
        i = 0
        classroom_avg = 0.0
        for score in score_list:
            if i >= 1 and score.value == score_list[i - 1].value:
                score.rank = i  # This helps manage ex-aequo ranks
            else:
                score.rank = i + 1
            score.save()
            classroom_avg += score.value
            i += 1
        classroom_avg /= len(score_list)
        score_matrix[group_name]['classroom_avg'] = round(classroom_avg, 2)

    classroom_total = 0.0
    for student in student_list:
        try:
            sg_score = SessionGroupScore.objects.get(session_group=session_group, student=student, subject__isnull=True)
        except SessionGroupScore.DoesNotExist:
            sg_score = SessionGroupScore.objects.create(session_group=session_group, student=student,
                                                        value1=0, value2=0, value=0)
        classroom_total += sg_score.value
    classroom_general_avg = round(classroom_total / len(student_list), 2)
    classroom_general_avg_min = SessionGroupScore.objects.filter(session_group=session_group, subject__isnull=True).order_by('value')[0]
    classroom_general_avg_max = SessionGroupScore.objects.filter(session_group=session_group, subject__isnull=True).order_by('-value')[0]

    student_score_matrix = OrderedDict()
    i = -1
    for student in student_list:
        i += 1
        total_score = 0.0
        for group in subject_group_list:
            group_name = 'Group%d' % group
            group_total_score = score_matrix[group_name]['score_list'][i]['total_score']
            group_total_coef = score_matrix[group_name]['score_list'][i]['total_coef']
            student_score_matrix[group_name] = {
                'total_score': group_total_score,
                'total_coef': group_total_coef,
                'avg_score': score_matrix[group_name]['score_list'][i]['score'],
                'classroom_avg': score_matrix[group_name]['classroom_avg'],
                'subject_list': []
            }
            for obj in subject_coefficient_list:
                if obj.group == group:
                    subject = obj.subject
                    score = score_matrix[subject.slug]['score_list'][i]
                    teacher_name = subject.get_teacher(classroom).member.full_name
                    student_score_matrix[group_name]['subject_list'].append({
                        'teacher_name': escape(teacher_name).encode('ascii', 'xmlcharrefreplace'),
                        'subject_name': escape(subject.name).encode('ascii', 'xmlcharrefreplace'),
                        'coefficient': obj.coefficient,
                        'total_score': obj.coefficient * score.value,
                        'score': score,
                        'max': score_matrix[subject.slug]['max'],
                        'min': score_matrix[subject.slug]['min'],
                        'classroom_avg': score_matrix[subject.slug]['classroom_avg']
                    })
            total_score += group_total_score

        sg_score = SessionGroupScore.objects.get(student=student, session_group=session_group, subject__isnull=True)

        start, end = session_group.starts_on, session_group.ends_on
        absence_count_justified = DisciplineLogEntry.objects\
            .filter(student=student, item=absence, is_justified=True, happened_on__range=(start, end)).count()
        absence_count_non_justified = DisciplineLogEntry.objects\
            .filter(student=student, item=absence, is_justified=False, happened_on__range=(start, end)).count()
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=absence, is_justified=True, happened_on__range=(start, end)).aggregate(Sum('count'))
            absence_duration_justified = aggr['count__sum']
        except IndexError:
            absence_duration_justified = 0
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=absence, is_justified=False, happened_on__range=(start, end)).aggregate(Sum('count'))
            absence_duration_non_justified = aggr['count__sum']
        except IndexError:
            absence_duration_non_justified = 0
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=lateness, is_justified=True, happened_on__range=(start, end)).aggregate(Sum('count'))
            lateness_count_justified = aggr['count__sum']
        except IndexError:
            lateness_count_justified = 0
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=lateness, is_justified=False, happened_on__range=(start, end)).aggregate(Sum('count'))
            lateness_count_non_justified = aggr['count__sum']
        except IndexError:
            lateness_count_non_justified = 0
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=warning, happened_on__range=(start, end)).aggregate(Sum('count'))
            warning_count = aggr['count__sum']
        except IndexError:
            warning_count = 0
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=censure, happened_on__range=(start, end)).aggregate(Sum('count'))
            censure_count = aggr['count__sum']
        except IndexError:
            censure_count = 0
        try:
            aggr = DisciplineLogEntry.objects\
                .filter(student=student, item=exclusion, happened_on__range=(start, end)).aggregate(Sum('count'))
            exclusion_count = aggr['count__sum']
        except IndexError:
            exclusion_count = 0

        from ikwen.conf import settings as ikwen_settings
        media_root = getattr(settings, 'MEDIA_ROOT')
        head_organization_logo = media_root + report_card_header.head_organization_logo.name
        if not os.path.isfile(head_organization_logo):
            head_organization_logo = ''
        school_logo = media_root + config.logo.name
        if not os.path.isfile(school_logo):
            school_logo = ''
        student_photo = ikwen_settings.MEDIA_ROOT + student.photo.name
        if not os.path.isfile(student_photo):
            student_photo = ''

        context = Context({
            # Special Labels
            'label_school_year': _("School year").encode('ascii', 'xmlcharrefreplace'),
            'label_student_name': _("Student name").encode('ascii', 'xmlcharrefreplace'),
            'label_subjects': _("Subjects").encode('ascii', 'xmlcharrefreplace'),
            'label_results': _("Results").encode('ascii', 'xmlcharrefreplace'),
            'label_council_decision': _("Council decision").encode('ascii', 'xmlcharrefreplace'),
            # End special labels

            'ministry_logo': head_organization_logo,
            'school_logo': school_logo,
            'student_photo': student_photo,

            'country_name': escape(report_card_header.country_name).encode('ascii', 'xmlcharrefreplace'),
            'country_motto': escape(report_card_header.country_moto).encode('ascii', 'xmlcharrefreplace'),
            'head_organization': escape(report_card_header.head_organization).encode('ascii', 'xmlcharrefreplace'),
            'sequence_number': escape(session_group.name).encode('ascii', 'xmlcharrefreplace'),
            'school_address': escape(config.address).encode('ascii', 'xmlcharrefreplace'),
            'school_contact': escape(config.contact_phone).encode('ascii', 'xmlcharrefreplace'),
            'school_name': escape(config.company_name).encode('ascii', 'xmlcharrefreplace'),
            'school_motto': escape(config.slogan).encode('ascii', 'xmlcharrefreplace'),

            'school_year': "%d - %d" % (school_year, school_year + 1),
            'city_name': escape(config.city).encode('ascii', 'xmlcharrefreplace'),
            'classroom': classroom,
            'student': student,
            'first_name': escape(student.first_name).encode('ascii', 'xmlcharrefreplace'),
            'last_name': escape(student.last_name).encode('ascii', 'xmlcharrefreplace'),
            'classroom_name': escape(str(classroom).decode('utf8')).encode('ascii', 'xmlcharrefreplace'),
            'classroom_level_name': escape(str(classroom.level).decode('utf8')).encode('ascii', 'xmlcharrefreplace'),
            'student_score_matrix': student_score_matrix,
            'total_score': total_score,
            'total_coef': total_coefficient,
            'session_score': sg_score,
            'classroom_general_avg': classroom_general_avg,
            'classroom_general_avg_min': classroom_general_avg_min,
            'classroom_general_avg_max': classroom_general_avg_max,
            'absence_count_justified': absence_count_justified,
            'absence_duration_justified': absence_duration_justified,
            'absence_count_non_justified': absence_count_non_justified,
            'absence_duration_non_justified': absence_duration_non_justified,
            'lateness_count_justified': lateness_count_justified,
            'lateness_count_non_justified': lateness_count_non_justified,
            'warning_count': warning_count,
            'censure_count': censure_count,
            'exclusion_count': exclusion_count,
            'date_generated': date_generated
        })
        template = get_template('reporting/session_group_report_card.rml.html')
        xmlstring = template.render(context)
        pdfstr = trml2pdf.parseString(xmlstring)
        report_card = classroom_folder + slugify(str(student).decode('utf8')).capitalize() + '.pdf'
        f = open(report_card, 'w')
        f.write(pdfstr)
        batch.generated += 1
        batch.save()
