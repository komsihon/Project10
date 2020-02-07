# -*- coding: utf-8 -*-

# LOADING FIXTURES DOES NOT WORK BECAUSE Database connection 'foundation' is never found
# tests_views.py is an equivalent of these tests run by loading data into databases manually


import json
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest
from ikwen.partnership.models import PartnerProfile

from ikwen.billing.models import Invoice, IkwenInvoiceItem, InvoiceEntry

from ikwen.core.models import Service, OperatorWallet


def wipe_test_data(db=None):
    """
    This test was originally built with django-nonrel 1.6 which had an error when flushing the database after
    each test. So the flush is performed manually with this custom tearDown()
    """
    import ikwen_foulassi.foulassi.models
    import ikwen_foulassi.school.models
    import ikwen_foulassi.reporting.models
    import ikwen.core.models
    import ikwen.accesscontrol.models
    OperatorWallet.objects.using('wallets').all().delete()
    if db:
        aliases = [db]
    else:
        aliases = getattr(settings, 'DATABASES').keys()
    for alias in aliases:
        if alias == 'wallets':
            continue
        if not alias.startswith('test_'):
            continue
        Group.objects.using(alias).all().delete()
        for name in ('Teacher', 'Student', 'Parent', 'ParentProfile', 'SchoolConfig',
                     'Invoice', 'Payment', 'EventType', 'Event', ):
            model = getattr(ikwen_foulassi.foulassi.models, name)
            model.objects.using(alias).all().delete()
        for name in ('Level', 'Classroom', 'Subject', 'Session', 'SubjectSession', 'TeacherResponsibility'):
            model = getattr(ikwen_foulassi.school.models, name)
            model.objects.using(alias).all().delete()
        for name in ('ReportCardHeader', 'LessonReport', 'DisciplineReport', 'StudentDisciplineReport',
                     'SessionReport', 'SessionGroupReport', 'YearReport', 'ReportCardBatch'):
            model = getattr(ikwen_foulassi.reporting.models, name)
            model.objects.using(alias).all().delete()
        for name in ('Member',):
            model = getattr(ikwen.accesscontrol.models, name)
            model.objects.using(db).all().delete()
        for name in ('Application', 'Service', 'Config', 'ConsoleEventType', 'ConsoleEvent', 'Country', ):
            model = getattr(ikwen.core.models, name)
            model.objects.using(alias).all().delete()


class SchoolViewsTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['ikwen_members.yaml', 'setup_data.yaml']

    def setUp(self):
        self.client = Client()
        for fixture in self.fixtures:
            call_command('loaddata', fixture)

    def tearDown(self):
        wipe_test_data()

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', CACHES=None)
    def test_list_projects(self):
        """
        Lists projects with name contains the query 'q' and return a JSON Array of objects
        """
        self.client.login(username='member3', password='admin')
        callback = 'jsonp'
        response = self.client.get(reverse('ikwen:list_projects'), {'q': 'ik', 'callback': callback})
        self.assertEqual(response.status_code, 200)
        json_string = response.content[:-1].replace(callback + '(', '')
        json_response = json.loads(json_string)
        self.assertEqual(len(json_response['object_list']), 2)
