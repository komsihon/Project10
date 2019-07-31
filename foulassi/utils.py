# -*- coding: utf-8 -*-
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.translation import gettext as _
from permission_backend_nonrel.models import UserPermissionList
from permission_backend_nonrel.utils import add_permission_to_user

from ikwen.core.constants import FEMALE, MALE
from ikwen.core.utils import get_service_instance
from ikwen.accesscontrol.models import Member
from ikwen.accesscontrol.backends import UMBRELLA

from ikwen_foulassi.school.models import Classroom, get_subject_list, Score, Level
from ikwen_foulassi.foulassi.models import get_school_year, ParentProfile, EventType, Event, \
    ALL_SCORES_SET


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
    # ikwen_name = kwargs['ikwen_name']
    student_id = kwargs['student_id']
    parent_profile, update = ParentProfile.objects.get_or_create(member=user)
    student_fk_list = [student.id for student in parent_profile.student_list]
    if student_id in student_fk_list:
        return True
    # service = Service.objects.get(project_name_slug=ikwen_name)
    # db = service.database
    # add_database(db)
    # parent_email_list = [parent.email for parent in Parent.objects.using(db).filter(student=student_id)]
    # parent_phone_list = [parent.phone for parent in Parent.objects.using(db).filter(student=student_id)]
    # user_phone = slugify(user.phone).replace('-', '')
    # if user_phone in parent_phone_list or user.email in parent_email_list:
    #     try:
    #         student = Student.objects.using(db).get(pk=student_id)
    #         for parent in Parent.objects.using(db).filter(student=student):
    #             if user.email == parent.email or user.phone == parent.phone:
    #                 user.save(using=db)
    #                 parent.member = user  # Binds the ikwen Member as parent
    #                 parent.save(using=db)
    #                 break
    #     except:
    #         raise Http404("Student not found.")
    #     parent_profile.student_list.append(student)
    #     parent_profile.save()
    #     return True
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
    for classroom in Classroom.objects.filter(school_year=school_year):
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
            profile.student_list.remove(student)
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
