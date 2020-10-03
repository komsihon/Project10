import sys
import os
import logging
from datetime import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", 'ikwen.conf.settings')

from django.core.mail import EmailMessage
from django.utils.translation import ugettext as _, activate

from ikwen.core.models import Application, Service
from ikwen.core.utils import add_database, send_push
from ikwen.core.log import CRONS_LOGGING
from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_mail_content

from ikwen_foulassi.foulassi.models import Reminder, SchoolConfig
from ikwen_foulassi.foulassi.utils import check_setup_status


logging.config.dictConfig(CRONS_LOGGING)
logger = logging.getLogger('ikwen.crons')


DEBUG = False


def remind_staff():
    app = Application.objects.get(slug='foulassi')

    for school in Service.objects.filter(app=app):
        diff = datetime.now() - school.since
        if not DEBUG and diff.days < 7:
            print("Skipping school %s" % school.project_name)
            continue

        db = school.database
        add_database(db)

        school_config = SchoolConfig.objects.using(db).get(service=school)
        parents_reminder, change = Reminder.objects.using(db).get_or_create(type=Reminder.UNREGISTERED_PARENTS)
        diff = datetime.now() - parents_reminder.updated_on
        if not DEBUG and diff.days < 7:
            print("Skipping school %s" % school.project_name)
            continue

        print("Processing school %s" % school.project_name)

        if DEBUG:
            parents_reminder, students_reminder, estimated_loss = check_setup_status(school)
        else:
            try:
                parents_reminder, students_reminder, estimated_loss = check_setup_status(school)
            except:
                continue

        for member in Member.objects.using(db).filter(is_superuser=True):
            sender = 'ikwen Foulassi <no-reply@ikwen.com>'
            cta_url = school.admin_url
            activate(member.language)
            subject = _("Complete your school setup")
            extra_context = {'member_name': member.first_name, 'cta_url': cta_url,
                             'school_name': school_config.company_name, 'parents_reminder': parents_reminder,
                             'students_reminder': students_reminder, 'estimated_loss': estimated_loss}
            if DEBUG:
                html_content = get_mail_content(subject, template_name='foulassi/mails/school_setup_reminder.html',
                                                extra_context=extra_context)
            else:
                try:
                    html_content = get_mail_content(subject, template_name='foulassi/mails/school_setup_reminder.html',
                                                    extra_context=extra_context)
                except:
                    logger.error("Could not generate HTML content from template", exc_info=True)
                    continue

            msg = EmailMessage(subject, html_content, sender, [member.email])
            msg.content_subtype = "html"

            if not DEBUG:
                print("Sending email to %s ..." % member.email)

            msg.send()

            if not DEBUG:
                print("Email sent")

            body = "%s" % school.project_name
            if students_reminder:
                body += _("has %(missing)s unregistered student(s)"
                          % {'missing': students_reminder.missing})
                send_push(member, subject, body, cta_url)
                continue
            if parents_reminder:
                body += _("has %(missing)s student(s) who have(has) not yet parent(s) contacts"
                          % {'missing': parents_reminder.missing})
            send_push(school, member, subject, body, cta_url)


if __name__ == '__main__':
    try:
        DEBUG = sys.argv[1] == 'debug'
    except IndexError:
        DEBUG = False
    if DEBUG:
        remind_staff()
    else:
        try:
            remind_staff()
        except:
            logger.error(u"Fatal error occured", exc_info=True)


