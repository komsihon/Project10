from django.conf import settings
from django.template import Context
from django.template.defaultfilters import slugify
from django.template.loader import get_template

from ikwen_foulassi.foulassi.models import Student
from ikwen_foulassi.school.models import Session
from ikwen_foulassi.reporting.utils import REPORT_CARDS_FOLDER


def render_all_scores_set(event, request):
    session = Session.objects.select_related('session_group').get(pk=event.object_id_list[0])
    c = Context({'event': event, 'session': session})
    template_name = 'foulassi/events/session_scores_all_set.html'
    html_template = get_template(template_name)
    return html_template.render(c)


def render_report_cards_generated(event, request):
    session = Session.objects.select_related('session_group').get(pk=event.object_id_list[0])
    if session.order_number % 2 == 0:  # Isolated session
        archive = '%s_%d-%d/%s/%s.zip' % (REPORT_CARDS_FOLDER, session.school_year, session.school_year + 1,
                                       slugify(session.session_group.name).capitalize(), slugify(session.name).capitalize())
    else:  # Two session with the session group altogether
        archive = '%s_%d-%d/%s.zip' % (REPORT_CARDS_FOLDER, session.school_year, session.school_year + 1,
                                    slugify(session.session_group.name).capitalize())
    c = Context({'event': event, 'session': session, 'archive': archive})
    template_name = 'foulassi/events/report_cards_generated.html'
    html_template = get_template(template_name)
    return html_template.render(c)


def render_report_cards_failed_to_generate(event, request):
    session = Session.objects.select_related('session_group').get(pk=event.object_id_list[0])
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
    from ikwen.conf import settings as ikwen_settings
    c = Context({'event': event, 'service': event.service, 'student': student,
                 'MEMBER_AVATAR': ikwen_settings.MEMBER_AVATAR, 'IKWEN_MEDIA_URL': ikwen_settings.MEDIA_URL})
    return html_template.render(c)
