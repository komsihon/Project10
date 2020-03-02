from django.core.urlresolvers import reverse
from django.template import Context
from django.template.loader import get_template

from ikwen.conf import settings as ikwen_settings
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member
from ikwen_foulassi.foulassi.models import Student, KidRequest
from ikwen_foulassi.school.models import Session, Classroom


def render_all_scores_set(event, request):
    try:
        session = Session.objects.select_related('session_group').get(pk=event.object_id_list[0])
    except Session.DoesNotExist:
        event.delete()
        return ''
    has_perm = request.user.has_perm('reporting.ik_manage_reporting')
    c = Context({'event': event, 'session': session, 'has_perm': has_perm})
    template_name = 'foulassi/events/session_scores_all_set.html'
    html_template = get_template(template_name)
    return html_template.render(c)


def render_report_cards_generated(event, request):
    try:
        session = Session.objects.select_related('session_group').get(pk=event.object_id_list[0])
    except Session.DoesNotExist:
        event.delete()
        return ''
    classroom = None
    try:
        classroom = Classroom.objects.get(pk=event.object_id_list[1])
    except IndexError:
        pass
    except Classroom.DoesNotExist:
        event.delete()
        return ''
    if classroom:
        report_cards_download_url = reverse('reporting:report_card_download_list', args=(session.id, classroom.id))
        c = Context({'event': event, 'session': session,
                     'classroom': classroom, 'report_cards_download_url': report_cards_download_url})
        template_name = 'foulassi/events/classroom_report_cards_generated.html'
    else:
        c = Context({'event': event, 'session': session})
        template_name = 'foulassi/events/report_cards_generated.html'
    html_template = get_template(template_name)
    return html_template.render(c)


def render_report_cards_failed_to_generate(event, request):
    try:
        session = Session.objects.select_related('session_group').get(pk=event.object_id_list[0])
    except Session.DoesNotExist:
        event.delete()
        return ''
    c = Context({'event': event, 'session': session})
    template_name = 'foulassi/events/report_cards_failed_to_generate.html'
    html_template = get_template(template_name)
    return html_template.render(c)


def render_student_excluded_event(event, request):
    try:
        student = Student.objects.get(pk=event.object_id)
    except Student.DoesNotExist:
        return ''
    html_template = get_template('school/events/student_excluded.html')
    entries_count = len(student.entries)
    more_entries = entries_count - 3  # Number to show on the "View more" button
    c = Context({'event': event, 'service': event.service, 'student': student,
                 'MEMBER_AVATAR': ikwen_settings.MEMBER_AVATAR, 'IKWEN_MEDIA_URL': ikwen_settings.MEDIA_URL})
    return html_template.render(c)


def render_parent_request_kid(event, request):
    try:
        kid_request = KidRequest.objects.get(pk=event.object_id_list[0])
    except KidRequest.DoesNotExist:
        event.delete()
        return ''
    parent = Member.objects.using(UMBRELLA).get(pk=kid_request.parent_id)
    html_template = get_template('foulassi/events/parent_kid_request.html')
    c = Context({'event': event, 'parent': parent, 'kids_details': kid_request.kids_details,
                 'MEMBER_AVATAR': ikwen_settings.MEMBER_AVATAR, 'IKWEN_MEDIA_URL': ikwen_settings.MEDIA_URL})
    return html_template.render(c)
