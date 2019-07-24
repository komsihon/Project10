# -*- coding: utf-8 -*-

# LOADING FIXTURES DOES NOT WORK BECAUSE Database connection 'foundation' is never found
# tests_views.py is an equivalent of these tests run by loading data into databases manually


import json
from datetime import datetime, timedelta
from time import strptime

from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest

from ikwen.core.utils import get_service_instance

from ikwen_foulassi.foulassi.tests_views import wipe_test_data

from ikwen_foulassi.reporting.models import DisciplineReport, StudentDisciplineReport

from ikwen_foulassi.school.models import Level, Classroom, DisciplineItem

from reporting.utils import set_daily_counters_many


class ReportingUtilsTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['fls_setup_data.yaml', 'fls_members.yaml', 'people.yaml', 'school_setup.yaml']

    def setUp(self):
        self.client = Client()
        for fixture in self.fixtures:
            call_command('loaddata', fixture)

    def tearDown(self):
        wipe_test_data()

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', CACHES=None)
    def test_set_daily_counters_many(self):
        """
        The page must be reachable
        """
        config = get_service_instance().config
        config.back_to_school_date = datetime.now() - timedelta(days=9)
        config.save()
        item = DisciplineItem.objects.get(slug='absence')
        level = Level.objects.get(slug='6eme')
        classroom = Classroom.objects.get(pk='60e011bd0b53137b33471d81')
        discipline_report, update = DisciplineReport.objects.get_or_create(discipline_item=item, level=None,
                                                                           classroom=None)
        level_discipline_report, update = DisciplineReport.objects.get_or_create(discipline_item=item, level=level,
                                                                                 classroom=None)
        classroom_discipline_report, update = DisciplineReport.objects.get_or_create(discipline_item=item, level=None,
                                                                                     classroom=classroom)
        set_daily_counters_many(discipline_report, level_discipline_report, classroom_discipline_report)
        for tracker_obj in (discipline_report, level_discipline_report, classroom_discipline_report):
            history_fields = [field for field in tracker_obj.__dict__.keys() if field.endswith('_history')]
            for name in history_fields:
                self.assertEqual(len(tracker_obj.__getattribute__(name)), 10)
