from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext as _
from ikwen_foulassi.foulassi.models import Student, Teacher, Event
from ikwen_foulassi.school.models import Level, Score
from ikwen_foulassi.reporting.models import SessionReport, ReportCardBatch


def create_permissions():
    student_ct = ContentType.objects.get_for_model(Student)
    Permission.objects.create(codename='ik_manage_student', name=_('Access students info'), content_type=student_ct)
    teacher_ct = ContentType.objects.get_for_model(Teacher)
    Permission.objects.create(codename='ik_manage_teacher', name=_('Manage teachers'), content_type=teacher_ct)
    level_ct = ContentType.objects.get_for_model(Level)
    Permission.objects.create(codename='ik_manage_school', name=_('Manage school setup'), content_type=level_ct)
    score_ct = ContentType.objects.get_for_model(Score)
    Permission.objects.create(codename='ik_access_scores', name=_('Access student scores'), content_type=score_ct)
    report_ct = ContentType.objects.get_for_model(SessionReport)
    Permission.objects.create(codename='ik_view_dashboard', name=_('View dashboard'), content_type=report_ct)
    batch_ct = ContentType.objects.get_for_model(ReportCardBatch)
    Permission.objects.create(codename='ik_manage_reporting', name=_('Manage report cards'), content_type=batch_ct)
    event_ct = ContentType.objects.get_for_model(Event)
    Permission.objects.create(codename='ik_view_event', name=_('View events'), content_type=event_ct)
