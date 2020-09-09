# -*- coding: utf-8 -*-

# LOADING FIXTURES DOES NOT WORK BECAUSE Database connection 'foundation' is never found
# tests_views.py is an equivalent of these tests run by loading data into databases manually


import json

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest

from ikwen.accesscontrol.models import Member
from ikwen.core.models import OperatorWallet
from ikwen.core.utils import add_database

from ikwen_foulassi.foulassi.models import Student, Parent, ParentProfile


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
    databases = getattr(settings, 'DATABASES')
    for alias in aliases:
        if alias == 'wallets':
            continue
        if not databases[alias]['NAME'].startswith('test_'):
            continue
        Group.objects.using(alias).all().delete()
        for name in ('Teacher', 'Student', 'Parent', 'ParentProfile', 'SchoolConfig',
                     'Invoice', 'Payment', 'EventType', 'Event', ):
            model = getattr(ikwen_foulassi.foulassi.models, name)
            model.objects.using(alias).all().delete()
        for name in ('Level', 'Classroom', 'Subject', 'Session', 'SubjectCoefficient', 'TeacherResponsibility',
                     'Assignment', 'Homework', 'DisciplineItem', 'DisciplineLogEntry', 'Justificatory',
                     'Lesson', 'Score', 'ScoreUpdateRequest', 'SessionGroup', 'SessionGroupScore'):
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


class FoulassiViewsTestCase(unittest.TestCase):
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

    # @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True,
    #                    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    # def test_KidList_with_parent_having_registered_kids(self):
    #     """
    #     KidList Page must be reachable and suggest kids
    #     """
    #     self.client.login(username='member6', password='admin')
    #     response = self.client.get(reverse('foulassi:kid_list'))
    #     self.assertEqual(response.status_code, 200)
    #     suggestion_list = response.context['suggestion_list']
    #     kid_list = response.context['kid_list']
    #     self.assertEqual(len(suggestion_list), 1)
    #     self.assertEqual(suggestion_list[0].id, '584f03a7bbd6b46a8fc0c241')
    #     self.assertEqual(kid_list, [])
    #
    # @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True,
    #                    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    # def test_KidList_accept_suggestion(self):
    #     """
    #     Accepting suggested Kid sets authenticated User as as Parent.member
    #     """
    #     db = 'test_collegembakop'
    #     add_database(db)
    #     call_command('loaddata', 'people.yaml', database=db)
    #     self.client.login(username='member6', password='admin')
    #     response = self.client.get(reverse('foulassi:kid_list'),
    #                                data={'action': 'accept_suggestion', 'student_id': '584f03a7bbd6b46a8fc0c241'})
    #     json_resp = json.loads(response.content)
    #     self.assertTrue(json_resp['success'])
    #     member = Member.objects.using(db).get(username='member6')
    #     parent = Parent.objects.using(db).get(pk='574fb307c0cbed6b4f246a81')
    #     parent_profile = ParentProfile.objects.get(member=member)
    #     self.assertEqual(parent.member, member)
    #     self.assertEqual(parent_profile.student_fk_list[0], '584f03a7bbd6b46a8fc0c241')

    # @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True,
    #                    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    # def test_KidList_refuse_suggestion(self):
    #     """
    #     Refusing suggested Kid deletes the Parent Object
    #     """
    #     self.client.login(username='member6', password='admin')
    #     response = self.client.get(reverse('foulassi:kid_list'),
    #                                data={'action': 'refuse_suggestion', 'student_id': '584f03a7bbd6b46a8fc0c241'})
    #     json_resp = json.loads(response.content)
    #     self.assertTrue(json_resp['success'])
    #     school = Student.objects.get(pk='584f03a7bbd6b46a8fc0c241').school
    #     db = school.database
    #     self.assertRaises(Parent.DoesNotExist, Parent.objects.using(db).get, pk='574fb307c0cbed6b4f246a81')

    # @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True,
    #                    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    # def test_KidDetail_with_unauthorized_parent(self):
    #     """
    #     Unauthorized parent is redirected
    #     """
    #     self.client.login(username='member4', password='admin')
    #     response = self.client.get(reverse('foulassi:kid_detail', args=('collegembakop', '584f03a7bbd6b46a8fc0c241')))
    #     self.assertEqual(response.status_code, 302)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True,
                       CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    def test_KidDetail_with_authorized_parent(self):
        """
        Ensure Main page and tabs are accessible
        """
        db = 'test_collegembakop'
        add_database(db)
        for fixture in ['fls_setup_data.yaml', 'school_setup.yaml', 'people.yaml']:
            call_command('loaddata', fixture, database=db)
        self.client.login(username='member4', password='admin')
        kid_detail_url = reverse('foulassi:kid_detail', args=('collegembakop', '584f03a7bbd6b46a8fc0c244'))
        response = self.client.get(kid_detail_url)
        self.assertEqual(response.status_code, 200)
        student = response.context['student']
        self.assertEqual(student.id, '584f03a7bbd6b46a8fc0c244')

        response = self.client.get(kid_detail_url, data={'tab': 'billing'})
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True,
                       CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    def test_KidDetail_tab_assignments(self):
        """
        Ensure tab assignments is accessible
        """
        db = 'test_collegembakop'
        add_database(db)
        for fixture in ['fls_setup_data.yaml', 'school_setup.yaml', 'people.yaml']:
            call_command('loaddata', fixture, database=db)
        self.client.login(username='member4', password='admin')
        kid_detail_url = reverse('foulassi:kid_detail', args=('collegembakop', '584f03a7bbd6b46a8fc0c244'))
        response = self.client.get(kid_detail_url, data={'tab': 'assignments'})
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True,
                       CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    def test_KidDetail_tab_scores(self):
        """
        Ensure tab scores is accessible
        """
        db = 'test_collegembakop'
        add_database(db)
        for fixture in ['fls_setup_data.yaml', 'school_setup.yaml', 'people.yaml']:
            call_command('loaddata', fixture, database=db)
        self.client.login(username='member4', password='admin')
        kid_detail_url = reverse('foulassi:kid_detail', args=('collegembakop', '584f03a7bbd6b46a8fc0c244'))
        response = self.client.get(kid_detail_url, data={'tab': 'scores'})
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True,
                       CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    def test_KidDetail_tab_discipline(self):
        """
        Ensure tab discipline is accessible
        """
        db = 'test_collegembakop'
        add_database(db)
        for fixture in ['fls_setup_data.yaml', 'school_setup.yaml', 'people.yaml']:
            call_command('loaddata', fixture, database=db)
        self.client.login(username='member4', password='admin')
        kid_detail_url = reverse('foulassi:kid_detail', args=('collegembakop', '584f03a7bbd6b46a8fc0c244'))
        response = self.client.get(kid_detail_url, data={'tab': 'discipline'})
        self.assertEqual(response.status_code, 200)

    @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101', IS_IKWEN=True,
                       CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    def test_KidDetail_tab_billing(self):
        """
        Ensure tab billing is accessible
        """
        db = 'test_collegembakop'
        add_database(db)
        for fixture in ['fls_setup_data.yaml', 'school_setup.yaml', 'people.yaml']:
            call_command('loaddata', fixture, database=db)
        self.client.login(username='member4', password='admin')
        kid_detail_url = reverse('foulassi:kid_detail', args=('collegembakop', '584f03a7bbd6b46a8fc0c244'))
        response = self.client.get(kid_detail_url, data={'tab': 'billing'})
        self.assertEqual(response.status_code, 200)
