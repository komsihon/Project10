import sys
import os
import logging
from datetime import datetime
from datetime import timedelta

from django.core.urlresolvers import reverse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", 'ikwen.conf.settings')

from django.core.mail import EmailMessage
from django.utils.translation import ugettext as _, activate

from ikwen.core.models import Application, Service
from ikwen.core.utils import add_database
from ikwen.core.log import CRONS_LOGGING
from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_mail_content

from ikwen_foulassi.foulassi.models import Reminder, SchoolConfig, Parent, Student
from ikwen_foulassi.foulassi.utils import check_setup_status
from ikwen_foulassi.school.models import Assignment, Homework, Classroom


logging.config.dictConfig(CRONS_LOGGING)
logger = logging.getLogger('ikwen.crons')


DEBUG = False


def remind_parents():

    app = Application.objects.get(slug='foulassi')

    for school in Service.objects.filter(app=app):
        diff = datetime.now() - school.since
        if not DEBUG and diff.days < 7: # school should exist at least 1 week ago
            print("Skipping school %s" % school.project_name)
            continue

        db = school.database
        add_database(db)

        school_config = SchoolConfig.objects.using(db).get(service=school)

        for classroom in Classroom.objects.using(db).all():
            now = datetime.now()
            for assignment in classroom.assignment_set.filter(deadline=now.date() + timedelta(1)):
                for student in Student.objects.using(db).filter(classroom=classroom):
                    try:
                        # Test whether the homework was submitted
                        homework = student.homework_set.get(assignment=assignment)
                        continue
                    except:
                        for parent in Parent.objects.using(db).filter(student=student):
                            try:
                                parent_email = parent.get_email()
                                parent_name = parent.get_name()
                            except:
                                logger.error('A parent of %s has no contacts' % student.first_name)
                                continue
                            company_name = school_config.company_name
                            sender = '%s via ikwen Foulassi <no-reply@ikwen.com>' % company_name
                            try:
                                cta_url = 'https://go.ikwen.com' + reverse('foulassi:change_homework', args=(school_config.company_name_slug, student.pk, assignment.pk))
                            except:
                                cta_url = ''
                            if parent.member:
                                activate(parent.member.language)
                            subject = _("Less than 24 hours remain to turn back your kid's homework")
                            extra_context = {'parent_name': parent_name, 'cta_url': cta_url,
                                             'school_name': company_name,
                                             'student_name': student.first_name,
                                             'assignment': assignment,
                                             }
                            if DEBUG:
                                html_content = get_mail_content(subject,
                                                                template_name='foulassi/mails/unsubmitted_homework.html',
                                                                extra_context=extra_context)
                            else:
                                try:
                                    html_content = get_mail_content(subject,
                                                                    template_name='foulassi/mails/unsubmitted_homework.html',
                                                                    extra_context=extra_context)
                                except:
                                    logger.error("Could not generate HTML content from template", exc_info=True)
                                    continue

                            msg = EmailMessage(subject, html_content, sender, [parent_email, 'rsihon@gmail.com', 'silatchomsiaka@gmail.com'])
                            msg.content_subtype = "html"
                            print("Sending email to %s ..." % parent_email)
                            try:
                                msg.send()
                                print("Email sent")
                            except Exception as e:
                                print e.message


if __name__ == '__main__':
    try:
        DEBUG = sys.argv[1] == 'debug'
    except IndexError:
        DEBUG = False
    if DEBUG:
        remind_parents()
    else:
        try:
            remind_parents()
        except:
            logger.error(u"Fatal error occured", exc_info=True)