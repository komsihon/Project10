from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext as _, ugettext_lazy as __, pgettext
from ikwen.billing.models import Payment, MoMoTransaction
from ikwen_foulassi.foulassi.models import Student, Teacher, Event
from ikwen_foulassi.school.models import Level, Score, Subject
from ikwen_foulassi.reporting.models import SessionReport, ReportCardBatch
from ikwen_webnode.web.models import HomepageSection


group_secretary = _("Secretary")  # Simply causes this to appear in translation file
convocation = _("Parent Convocation")  # Simply causes this to appear in translation file
exclusion = _("Exclusion")  # Simply causes this to appear in translation file
lateness = _("Lateness")  # Simply causes this to appear in translation file
warning = pgettext("Student warning", "Warning")  # Simply causes this to appear in translation file
censure = _("Censure")  # Simply causes this to appear in translation file
absence = _("Absence")  # Simply causes this to appear in translation file
hours = _("Hour(s)")  # Simply causes this to appear in translation file
days = _("Day(s)")  # Simply causes this to appear in translation file


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
    hps_ct = ContentType.objects.get_for_model(HomepageSection)
    Permission.objects.create(codename='ik_webmaster', name=_('Website admin'), content_type=hps_ct)
    payment_ct = ContentType.objects.get_for_model(Payment)
    Permission.objects.create(codename='ik_manage_invoice', name=_('Manage invoices and payments'), content_type=payment_ct)
    transaction_ct = ContentType.objects.get_for_model(MoMoTransaction)
    Permission.objects.create(codename='ik_view_transaction_log', name=_('Manage transactions'), content_type=transaction_ct)


def do_test():
    student = Student.objects.all()[0]
    value = 15
    subject = Subject.objects.all()[0]
    text = __("Your kid %(student)s scored %(score)s in %(subject)s for the last evaluation." % {'student': student,
                                                                                                 'score': value,
                                                                                                 'subject': subject})
    print(unicode(text))


def do_test2():
    student = Student.objects.all()[0]
    value = 15
    subject = Subject.objects.all()[0]
    text = __("Your kid %(student)s scored %(score)s in %(subject)s for the last "
              "evaluation." % {'student': student, 'score': value, 'subject': subject})
    print(unicode(text))