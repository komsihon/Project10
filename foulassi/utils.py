# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta
from threading import Thread

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.template.defaultfilters import slugify
from django.utils.translation import ugettext_lazy as _, activate
from permission_backend_nonrel.models import UserPermissionList
from permission_backend_nonrel.utils import add_permission_to_user

from ikwen.core.constants import FEMALE, MALE
from ikwen.core.utils import get_service_instance, add_database, send_sms, get_sms_label, send_push
from ikwen.core.models import Service
from ikwen.accesscontrol.models import Member
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.billing.utils import set_dara_stats

from ikwen_foulassi.school.models import Classroom, get_subject_list, Score, Level
from ikwen_foulassi.foulassi.models import get_school_year, ParentProfile, EventType, Event, \
    ALL_SCORES_SET, SchoolConfig, Student, Reminder

from echo.utils import check_messaging_balance, count_pages

logger = logging.getLogger('ikwen')


def get_payment_confirmation_email_message(payment, parent_name, student_name):
    """
    Returns a tuple (mail subject, mail body) to send to
    member as receipt of Invoice payment.
    """
    config = get_service_instance().config
    invoice = payment.invoice
    subject = _("Invoice Payment Confirmation")
    message = _("Dear %(parent_name)s,<br><br>"
                "This is a payment receipt of %(currency)s %(amount).2f "
                "for Invoice <strong>No. %(invoice_number)s</strong> generated on %(date_issued)s "
                "for %(student_name)s. Below is a summary of your payment.<br><br>"
                "<span style='color: #666'>%(invoice_title)s</span><br><br>"
                "Thank you for your "
                "payment." % {'parent_name': parent_name,
                              'invoice_number': invoice.number,
                              'student_name': student_name,
                              'amount': payment.amount,
                              'currency': config.currency_symbol,
                              'date_issued': invoice.date_issued.strftime('%B %d, %Y'),
                              'invoice_title': invoice.get_title()})
    return subject, message


def get_payment_sms_text(payment, student_name):
    """
    Returns a tuple (mail subject, mail body) to send to
    member as receipt of Invoice payment.
    """
    config = get_service_instance().config
    message = _("Payment confirmation of %(currency)s %(amount).2f "
                "for school fees of %(student_name)s. "
                "Thank you." % {'amount': payment.amount,
                                'student_name': student_name,
                                'currency': config.currency_symbol})
    return message


def access_classroom(user):
    if user.is_anonymous():
        return False
    from ikwen_foulassi.foulassi.models import TEACHERS
    group_id = Group.objects.get(name=TEACHERS).id
    obj = UserPermissionList.objects.get(user=user)
    return user.has_perm('school.ik_manage_school') or group_id in obj.group_fk_list


def can_access_kid_detail(request, **kwargs):
    user = request.user
    if user.is_anonymous():
        return False
    student_id = kwargs['student_id']
    parent_profile, update = ParentProfile.objects.get_or_create(member=user)
    if student_id in parent_profile.student_fk_list:
        return True
    return False


def grant_teacher_permissions(request, *args, **kwargs):
    """
    Grant suitable permissions to teacher if he is actually one
    and does not have the permission
    """
    from ikwen_foulassi.foulassi.models import TEACHERS
    member = request.user
    obj = UserPermissionList.objects.get(user=member)
    grp = Group.objects.get(name=TEACHERS)
    is_teacher = grp.id in obj.group_fk_list
    if is_teacher:
        classroom_ct = ContentType.objects.get_for_model(Classroom)
        score_ct = ContentType.objects.get_for_model(Score)
        try:
            perm1 = Permission.objects.get(codename='ik_manage_classroom', content_type=classroom_ct)
        except Permission.DoesNotExist:
            perm1 = Permission.objects \
                .create(codename='ik_manage_classroom', name='Access classroom as teacher', content_type=classroom_ct)
        try:
            perm2 = Permission.objects.get(codename='ik_access_scores', content_type=score_ct)
        except Permission.DoesNotExist:
            perm2 = Permission.objects \
                .create(codename='ik_access_scores', name='Access student scores', content_type=score_ct)
        if not member.has_perm(perm1):
            add_permission_to_user(perm1, member)
        if not member.has_perm(perm2):
            add_permission_to_user(perm2, member)
    request.session['is_teacher'] = is_teacher


def check_all_scores_set(session):
    """
    Checks whether all scores have been set for all students
    in all classrooms for the current session. When it returns True,
    it means that we can generate report cards.
    """
    all_scores_set = True
    school_year = get_school_year()
    for classroom in Classroom.objects.filter(school_year=school_year, mark_students=True):
        try:
            student = classroom.student_set.filter(is_excluded=False)[0]
        except:
            continue
        subject_list = get_subject_list(classroom)
        for subject in subject_list:
            try:
                Score.objects.get(session=session, subject=subject, student=student)
            except:
                all_scores_set = False
                break
    if all_scores_set:
        session.all_scores_set_on = datetime.now()
        event_type, change = EventType.objects\
            .get_or_create(codename=ALL_SCORES_SET, renderer='ikwen_foulassi.foulassi.events.render_all_scores_set')
        try:
            Event.objects.raw_query({'object_id_list': {'$elemMatch': {'$eq': session.id}}}).filter(type=event_type)[0]
        except IndexError:
            Event.objects.create(type=event_type, object_id_list=[session.id])
    return all_scores_set


def remove_student_from_parent_profile(student, parent_email, parent_phone):
    """
    Removes a student from student_list of a Parent. This serves whenever
    a parent object is deleted or when email/phone are updated. Student is
    removed from student_list of parent with previous email/phone
    """
    member_list = list(Member.objects.using(UMBRELLA).filter(Q(email=parent_email) | Q(phone=parent_phone)))
    for profile in ParentProfile.objects.using(UMBRELLA).filter(member__in=member_list):
        try:
            profile.student_fk_list.remove(student.id)
            profile.save()
        except:
            continue


def set_student_counts():
    """
    Sets student_count for each Classroom, Level and School
    """
    total_boys, total_girls = 0, 0
    school_year = get_school_year()
    for level in Level.objects.filter(school_year=school_year):
        level_boys, level_girls = 0, 0
        for classroom in level.classroom_set.all():
            classroom.girls_count = classroom.student_set.filter(gender=FEMALE, is_excluded=False).count()
            classroom.boys_count = classroom.student_set.filter(gender=MALE, is_excluded=False).count()
            classroom.save()
            level_girls += classroom.girls_count
            level_boys += classroom.boys_count
        level.girls_count = level_girls
        level.boys_count = level_boys
        level.save()
        total_girls += level_girls
        total_boys += level_boys
    school = get_service_instance().config
    school.girls_count = total_girls
    school.boys_count = total_boys
    school.save()


def check_setup_status(school):
    """
    Checks what has been done so far regarding insertion of Students and Parent contacts
    """
    missing_parents = 0
    students_reminder = None
    db = school.database
    add_database(db)
    school_config = SchoolConfig.objects.using(db).get(service=school)
    now = datetime.now()
    if now - timedelta(days=7) != school_config.last_setup_status_check:
        return
    expected_student_count = school_config.expected_student_count
    student_count = Student.objects.using(db).filter(school=school).count()

    if student_count < expected_student_count:
        missing_students = expected_student_count - student_count
        missing_parents = missing_students
        print("%s missing students" % missing_students)
        students_reminder, change = Reminder.objects.using(db).get_or_create(type=Reminder.UNREGISTERED_STUDENTS)
        students_reminder.missing = missing_students
        students_reminder.save()
        for classroom in Classroom.objects.using(db).all():
            if classroom.student_set.all().count() < Classroom.STUDENT_THRESHOLD:
                classroom.has_student_reminder = True
                classroom.has_parent_reminder = True
            else:
                classroom.has_student_reminder = False
            classroom.save()
    else:
        Classroom.objects.using(db).update(has_student_reminder=False)

    for classroom in Classroom.objects.using(db).all():
        has_parent_reminder = False
        for student in classroom.student_set.all():
            if student.parent_set.all().count() == 0:
                has_parent_reminder = True
                missing_parents += 1
        classroom.has_parent_reminder = has_parent_reminder
        classroom.save()

    print("%s missing parents" % missing_parents)
    share_rate = school.billing_plan.tx_share_rate
    estimated_loss = missing_parents * school_config.my_kids_fees * (100 - share_rate)/100
    parents_reminder, update = Reminder.objects.using(db).get_or_create(type=Reminder.UNREGISTERED_PARENTS)
    parents_reminder.missing = missing_parents
    parents_reminder.estimated_loss = estimated_loss
    parents_reminder.save()

    return parents_reminder, students_reminder, estimated_loss


def share_payment_and_set_stats(invoice, payment_mean_slug):
    from daraja.models import DARAJA, Dara
    school = invoice.school
    service_umbrella = Service.objects.get(pk=school.id)
    partner = service_umbrella.retailer
    if not partner:
        return
    partner_is_dara = True if partner.app.slug == DARAJA else False
    if not (invoice.is_my_kids and partner_is_dara):
        return
    try:
        dara_share = Dara.objects.get(member=partner.member).share_rate
        ikwen_earnings = invoice.amount * (100 - dara_share) / 100
    except:
        logger.error("Error calculating Dara earnings. Invoice #%s - Service %s" % (
        invoice.number, service_umbrella.project_name))
        return
    partner_earnings = invoice.amount - ikwen_earnings
    add_database(partner.database)
    partner_original = Service.objects.select_related('member').using(partner.database).get(pk=partner.id)

    partner.raise_balance(partner_earnings, payment_mean_slug)
    from ikwen.conf.settings import IKWEN_SERVICE_ID
    service_partner = Service.objects.using(partner.database).get(pk=IKWEN_SERVICE_ID)
    set_dara_stats(partner_original, service_partner, invoice, partner_earnings)


def send_billed_sms(weblet, parent_list, text):
    config = weblet.config
    balance = check_messaging_balance(weblet)
    for parent in parent_list:
        member = parent.member
        phone = member.phone
        activate(member.language)
        page_count = count_pages(text)
        if balance.sms_count < page_count:
            break
        phone = slugify(phone).replace('-', '')
        if len(phone) == 9:
            phone = '237' + phone
        try:
            with transaction.atomic(using='wallets'):
                balance.sms_count -= page_count
                balance.save()
                send_sms(phone, text, get_sms_label(config))
        except:
            pass


def send_push_to_parents(foulassi_weblet, school_name, parent_list, body, target=None):
    for parent in parent_list:
        member = parent.member
        if member:
            activate(member.language)
            send_push(foulassi_weblet, member, school_name, body, target)
