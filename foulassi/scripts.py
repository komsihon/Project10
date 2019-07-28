from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from ikwen_foulassi.foulassi.models import Student, Teacher
from ikwen_foulassi.school.models import Level, Score
from ikwen_foulassi.reporting.models import SessionReport, ReportCardBatch


def create_permissions():
    student_ct = ContentType.objects.get_for_model(Student)
    Permission.objects.create(codename='ik_manage_student', name='Access students info', content_type=student_ct)
    teacher_ct = ContentType.objects.get_for_model(Teacher)
    Permission.objects.create(codename='ik_manage_teacher', name='Manage teachers', content_type=teacher_ct)
    level_ct = ContentType.objects.get_for_model(Level)
    Permission.objects.create(codename='ik_manage_school', name='Manage school setup', content_type=level_ct)
    score_ct = ContentType.objects.get_for_model(Score)
    Permission.objects.create(codename='ik_access_scores', name='Access student scores', content_type=score_ct)
    report_ct = ContentType.objects.get_for_model(SessionReport)
    Permission.objects.create(codename='ik_view_dashboard', name='View dashboard', content_type=report_ct)
    batch_ct = ContentType.objects.get_for_model(ReportCardBatch)
    Permission.objects.create(codename='ik_manage_reporting', name='Manage report cards', content_type=batch_ct)
