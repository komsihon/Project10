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
from ikwen.core.utils import add_database, send_push
from ikwen.core.log import CRONS_LOGGING
from ikwen.core.utils import get_mail_content

from ikwen_foulassi.foulassi.models import SchoolConfig, Parent, Student
from ikwen_foulassi.school.models import Classroom


logging.config.dictConfig(CRONS_LOGGING)
logger = logging.getLogger('ikwen.crons')


DEBUG = False


def remind_parents():

    app = Application.objects.get(slug='foulassi')
    try:
        foulassi = Service.objects.using('umbrella').get(project_name_slug='foulassi')
    except:
        foulassi = None

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
                        student.homework_set.get(assignment=assignment)
                        continue
                    except:
                        for parent in Parent.objects.using(db).select_related('member').filter(student=student):
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
                            member = parent.member
                            if member:
                                activate(member.language)
                            student_name = student.first_name
                            subject = _("Less than 24 hours remain to turn back your kid's homework")
                            extra_context = {'parent_name': parent_name, 'cta_url': cta_url,
                                             'school_name': company_name,
                                             'student_name': student_name,
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

                            body = _("%(student_name)s has not yet submit his homework of %(subject)s "
                                     % {'student_name': student_name, 'subject': subject})
                            if member:
                                send_push(foulassi, member, subject, body, cta_url)


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