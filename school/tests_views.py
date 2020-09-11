# -*- coding: utf-8 -*-

# LOADING FIXTURES DOES NOT WORK BECAUSE Database connection 'foundation' is never found
# tests_views.py is an equivalent of these tests run by loading data into databases manually


import json
from datetime import datetime
from time import strptime

from django.conf import settings
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.test.client import Client
from django.test.utils import override_settings
from django.utils import unittest

from ikwen.core.utils import get_service_instance
from ikwen_foulassi.foulassi.models import Student, Parent
from ikwen_foulassi.foulassi.tests_views import wipe_test_data
from ikwen_foulassi.school.models import Subject, Level, Classroom, Session, Score, SessionGroup

setattr(settings, 'CACHES', {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
setattr(settings, 'IKWEN_SERVICE_ID', '56eb6d04b37b3379b531b102')
setattr(settings, 'IKWEN_CONFIG_MODEL', 'foulassi.SchoolConfig')


class SchoolViewsTestCase(unittest.TestCase):
    """
    This test derives django.utils.unittest.TestCate rather than the default django.test.TestCase.
    Thus, self.client is not automatically created and fixtures not automatically loaded. This
    will be achieved manually by a custom implementation of setUp()
    """
    fixtures = ['fls_setup_data.yaml', 'school_setup.yaml', 'fls_members.yaml', 'people.yaml']

    def setUp(self):
        self.client = Client()
        for fixture in self.fixtures:
            call_command('loaddata', fixture)

    def tearDown(self):
        wipe_test_data()

    # def test_SubjectList(self):
    #     """
    #     The page must be reachable
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:subject_list'))
    #     self.assertEqual(response.status_code, 200)

    # def test_ChangeSubject_create_new(self):
    #     """
    #     Upon creation, name must be properly set
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:change_subject'))
    #     self.assertEqual(response.status_code, 200)
    #     name = 'Maths'
    #     self.client.post(reverse('school:change_subject'), {'name': name})
    #     subject = Subject.objects.get(name=name)
    #     self.assertIsNotNone(subject)
    #
    # @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101',
    #                    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    # def test_ChangeSubject_with_update_subject(self):
    #     """
    #     Upon update, name must be properly set
    #     """
    #     self.client.login(username='member2', password='admin')
    #     name = u'Mathématiques'
    #     self.client.post(reverse('school:change_subject', args=('59441ee04fc0c24f09e9d6da', )), {'name': name})
    #     subject = Subject.objects.get(pk='59441ee04fc0c24f09e9d6da')
    #     self.assertEqual(subject.name, name)

    # def test_LevelList(self):
    #     """
    #     The page must be reachable
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:level_list'))
    #     self.assertEqual(response.status_code, 200)
    #
    # def test_ChangeLevel_create_new(self):
    #     """
    #     Upon creation, if a list of subject is provided, it must be properly set
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:change_level'))
    #     self.assertEqual(response.status_code, 200)
    #     name = 'New level'
    #     self.client.post(reverse('school:change_level'),
    #                      {'name': name, 'registration_fees': 12000, 'first_instalment': 5000, 'second_instalment': 5000,
    #                       'third_instalment': 5000, 'subjects': '59441ee04fc0c24f09e9d6da:2:3:50:100,59441ee04fc0c24f09e9d6db:1:4:70:210'})
    #     level = Level.objects.get(name=name)
    #     self.assertEqual(len(level.subject_coefficient_list), 2)

    # def test_ChangeLevel_update_data(self):
    #     """
    #     Change must update Level information accordingly
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:change_level', args=('58d89d0b531e011b37b33471', )))
    #     self.assertEqual(response.status_code, 200)
    #     name = u'Prépa'
    #     subjects = '59441ee04fc0c24f09e9d6da:1:4:40:80,59441ee04fc0c24f09e9d6db:2:2:25:50,' \
    #                '59441ee04fc0c24f09e9d6dc:3:1:30:30,59441ee04fc0c24f09e9d6de:3:1:30:30'
    #     self.client.post(reverse('school:change_level', args=('58d89d0b531e011b37b33471', )),
    #                      {'name': name, 'registration_fees': 5000, 'first_instalment': 30000,
    #                       'second_instalment': 20000, 'third_instalment': 10000, 'subjects': subjects})
    #     level = Level.objects.get(pk='58d89d0b531e011b37b33471')
    #     self.assertEqual(level.name, name)
    #     self.assertEqual(level.registration_fees, 5000)
    #     self.assertEqual(level.first_instalment, 30000)
    #     self.assertEqual(level.second_instalment, 20000)
    #     self.assertEqual(level.third_instalment, 10000)
    #     self.assertEqual(len(level.subject_coefficient_list), 4)

    # def test_SessionGroupList(self):
    #     """
    #     The page must be reachable
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:sessiongroup_list'))
    #     self.assertEqual(response.status_code, 200)
    #
    # def test_ChangeSessionGroup_create_new(self):
    #     """
    #     Upon creation, name must be properly set
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:change_sessiongroup'))
    #     self.assertEqual(response.status_code, 200)
    #     name = '1er trimestre'
    #     now = datetime.now().strftime('%Y-%m-%d')
    #     self.client.post(reverse('school:change_sessiongroup'),
    #                      data={'name': name, 'starts_on': now, 'ends_on': now})
    #     session = SessionGroup.objects.get(name=name)
    #     self.assertIsNotNone(session)
    #
    # def test_ChangeSessionGroup_update(self):
    #     """
    #     Upon update, name must be properly set
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:change_sessiongroup', args=('5e5cdabe396b4880ccebbd51', )))
    #     self.assertEqual(response.status_code, 200)
    #     name = u'Trimestre Premier'
    #     now = datetime.now().strftime('%Y-%m-%d')
    #     self.client.post(reverse('school:change_sessiongroup', args=('5e5cdabe396b4880ccebbd51', )),
    #                      data={'name': name, 'starts_on': now, 'ends_on': now})
    #     session = SessionGroup.objects.get(pk='5e5cdabe396b4880ccebbd51')
    #     self.assertEqual(session.name, name)
    #
    # def test_SessionList(self):
    #     """
    #     The page must be reachable
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:session_list'))
    #     self.assertEqual(response.status_code, 200)
    #
    # def test_ChangeSession_create_new(self):
    #     """
    #     Upon creation, name must be properly set
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:change_session'))
    #     self.assertEqual(response.status_code, 200)
    #     name = u'Première Séquence'
    #     now = datetime.now().strftime('%Y-%m-%d')
    #     self.client.post(reverse('school:change_session'),
    #                      data={'session_group': '5e5cdabe396b4880ccebbd51', 'name': name, 'starts_on': now, 'ends_on': now})
    #     session = Session.objects.get(name=name)
    #     self.assertIsNotNone(session)
    #
    # def test_ChangeSession_update(self):
    #     """
    #     Upon update, name must be properly set
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:change_session', args=('58b217ec25de1dd789524fc1', )))
    #     self.assertEqual(response.status_code, 200)
    #     name = u'Séquence Première'
    #     now = datetime.now().strftime('%Y-%m-%d')
    #     self.client.post(reverse('school:change_session', args=('58b217ec25de1dd789524fc1', )),
    #                      data={'session_group': '5e5cdabe396b4880ccebbd51','name': name, 'starts_on': now, 'ends_on': now})
    #     session = Session.objects.get(pk='58b217ec25de1dd789524fc1')
    #     self.assertEqual(session.name, name)

    def test_ClassroomList(self):
        """
        The page must be reachable
        """
        self.client.login(username='member2', password='admin')
        response = self.client.get(reverse('school:classroom_list'))
        self.assertEqual(response.status_code, 200)

    def test_ChangeClassroom(self):
        """
        Adding a Classroom creates the Object
        """
        self.client.login(username='member2', password='admin')
        response = self.client.get(reverse('school:change_classroom'))
        self.assertEqual(response.status_code, 200)
        name = '1'
        subjects = '59441ee04fc0c24f09e9d6da:1:4:40:80,59441ee04fc0c24f09e9d6db:2:2:25:50,' \
                   '59441ee04fc0c24f09e9d6dc:3:1:30:30'
        self.client.post(reverse('school:change_classroom'),
                         {'level': '58d89d0b531e011b37b33471', 'name': name,
                          'registration_fees': 15000, 'first_instalment': 0, 'second_instalment': 0,
                          'third_instalment': 0, 'subjects': subjects})
        classroom = Classroom.objects.get(level='58d89d0b531e011b37b33471', name=name)
        self.assertEqual(len(classroom.subject_coefficient_list), 3)

    def test_ChangeClassroom_update_data(self):
        """
        Change must update Classroom information accordingly
        """
        self.client.login(username='member2', password='admin')
        response = self.client.get(reverse('school:change_classroom', args=('60e011bd0b53137b33471d81', )))
        self.assertEqual(response.status_code, 200)
        name = u'6ème A'
        subjects = '59441ee04fc0c24f09e9d6da:1:4:40:80,59441ee04fc0c24f09e9d6db:2:2:25:50,' \
                   '59441ee04fc0c24f09e9d6dc:3:1:30:30,59441ee04fc0c24f09e9d6de:3:1:30:30'
        self.client.post(reverse('school:change_classroom', args=('60e011bd0b53137b33471d81', )),
                         {'level': '58d89d0b531e011b37b33471', 'name': name, 'professor': '584f03a7bbd6b46a85db279a',
                          'registration_fees': 5000, 'first_instalment': 30000, 'second_instalment': 20000,
                          'third_instalment': 10000, 'subjects': subjects})
        classroom = Classroom.objects.get(pk='60e011bd0b53137b33471d81')
        self.assertEqual(classroom.name, name)
        self.assertEqual(classroom.registration_fees, 5000)
        self.assertEqual(classroom.first_instalment, 30000)
        self.assertEqual(classroom.second_instalment, 20000)
        self.assertEqual(classroom.third_instalment, 10000)
        self.assertEqual(classroom.professor.id, '584f03a7bbd6b46a85db279a')
        self.assertEqual(len(classroom.subject_coefficient_list), 4)

    def test_ClassroomDetail(self):
        """
        Ensure ClassroomDetail Page is reachable
        """

        self.client.login(username='member4', password='admin')
        response = self.client.get(reverse('school:classroom_detail', args=('60e011bd0b53137b33471d81', )))
        self.assertEqual(response.status_code, 200)

    def test_ClassroomDetail_add_lesson(self):
        """
        Ensure ClassroomDetail Page is reachable
        """
        now = datetime.now()
        config = get_service_instance().config
        config.back_to_school_date = datetime(now.year, 9, 1, 7, 30)
        config.save()
        self.client.login(username='member4', password='admin')
        response = self.client.get(reverse('school:classroom_detail', args=('60e011bd0b53137b33471d81', )),
                                   data={'action': 'add_lesson', 'subject_id': '59441ee04fc0c24f09e9d6da',
                                         'title': 'Arithmetic', 'hours_count': 2, 'is_complete': 'yes'})
        json_resp = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json_resp['success'])

    # @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101',
    #                    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    # def test_ClassroomDetail_with_action_mark(self):
    #     """
    #     Sets the scores of the students for the given subject
    #     """
    #     session_id = '58b217ec25de1dd789524fc2'
    #     subject_id = '59441ee04fc0c24f09e9d6da'
    #     classroom1_id = '60e011bd0b53137b33471d81'
    #     classroom2_id = '60e011bd0b53137b33471d82'
    #     level_id = '58d89d0b531e011b37b33471'
    #     s1_id = '584f03a7bbd6b46a8fc0c241'
    #     s2_id = '584f03a7bbd6b46a8fc0c242'
    #     s3_id = '584f03a7bbd6b46a8fc0c243'
    #     s4_id = '584f03a7bbd6b46a8fc0c244'
    #     s5_id = '584f03a7bbd6b46a8fc0c245'
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:classroom_detail', args=(classroom1_id, )))
    #     self.assertEqual(response.status_code, 200)
    #     scores1 = [{'student_id': s1_id, 'score': 9},
    #                {'student_id': s2_id, 'score': 13.5}]
    #     scores2 = [{'student_id': s3_id, 'score': 14},
    #                {'student_id': s4_id, 'score': 11},
    #                {'student_id': s5_id, 'score': 8}]
    #     self.client.post(reverse('school:classroom_detail', args=('60e011bd0b53137b33471d81', )),
    #                      {'action': 'mark', 'session_id': session_id, 'subject_id': subject_id,
    #                      'classroom_id': classroom1_id, 'scores': json.dumps(scores1)})
    #     self.client.post(reverse('school:classroom_detail', args=('60e011bd0b53137b33471d82', )),
    #                      {'action': 'mark', 'session_id': session_id, 'subject_id': subject_id,
    #                      'classroom_id': classroom2_id, 'scores': json.dumps(scores2)})
    #     Score.objects.get(session=session_id, subject=subject_id, student=s1_id, value=9)
    #     Score.objects.get(session=session_id, subject=subject_id, student=s2_id, value=13.5)
    #     classroom1_stats = SubjectSession.objects.get(session=session_id, subject=subject_id, classroom=classroom1_id)
    #     classroom2_stats = SubjectSession.objects.get(session=session_id, subject=subject_id, classroom=classroom2_id)
    #     level_stats = SubjectSession.objects.get(session=session_id, subject=subject_id, level=level_id)
    #
    #     self.assertListEqual(classroom1_stats.boys_participation_history, [0, 2])
    #     self.assertListEqual(classroom1_stats.boys_highest_score_history, [0, 13.5])
    #     self.assertListEqual(classroom1_stats.boys_lowest_score_history, [0, 9])
    #     self.assertListEqual(classroom1_stats.boys_success_history, [0, 1])
    #     self.assertListEqual(classroom1_stats.boys_avg_score_history, [0, 11.25])
    #
    #     self.assertListEqual(classroom2_stats.boys_participation_history, [0, 1])
    #     self.assertListEqual(classroom2_stats.boys_highest_score_history, [0, 8])
    #     self.assertListEqual(classroom2_stats.boys_lowest_score_history, [0, 8])
    #     self.assertListEqual(classroom2_stats.boys_success_history, [0, 0])
    #     self.assertListEqual(classroom2_stats.boys_avg_score_history, [0, 8])
    #
    #     self.assertListEqual(classroom2_stats.girls_participation_history, [0, 2])
    #     self.assertListEqual(classroom2_stats.girls_highest_score_history, [0, 14])
    #     self.assertListEqual(classroom2_stats.girls_lowest_score_history, [0, 11])
    #     self.assertListEqual(classroom2_stats.girls_success_history, [0, 2])
    #     self.assertListEqual(classroom2_stats.girls_avg_score_history, [0, 12.5])
    #
    #     self.assertListEqual(level_stats.boys_participation_history, [0, 3])
    #     self.assertListEqual(level_stats.boys_highest_score_history, [0, 13.5])
    #     self.assertListEqual(level_stats.boys_lowest_score_history, [0, 8])
    #     self.assertListEqual(level_stats.boys_success_history, [0, 1])
    #     self.assertListEqual(level_stats.boys_avg_score_history, [0, 10.17])
    #
    #     self.assertListEqual(level_stats.girls_participation_history, [0, 2])
    #     self.assertListEqual(level_stats.girls_highest_score_history, [0, 14])
    #     self.assertListEqual(level_stats.girls_lowest_score_history, [0, 11])
    #     self.assertListEqual(level_stats.girls_success_history, [0, 2])
    #     self.assertListEqual(level_stats.girls_avg_score_history, [0, 12.5])
    #
    # @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101',
    #                    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    # def test_ChangeStudent_add_student(self):
    #     """
    #     Calling ChangeStudent with unexisting should create a new
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:change_student'))
    #     self.assertEqual(response.status_code, 200)
    #     first_name = u'Francis'
    #     last_name = u'Mowa'
    #     dob = u'1986-04-05'
    #     p = [{'id': '', 'member_id': '', 'name': 'Nguetchuissi Richard',
    #           'phone': '690000000', 'email': 'nguetch@yahoo.fr', 'relation': 'Father'}]
    #     parents = json.dumps(p)
    #     self.client.post(reverse('school:change_student'),
    #                      {'action': 'change', 'classroom': '60e011bd0b53137b33471d81',
    #                       'first_name': first_name, 'last_name': last_name, 'gender': 'Male',
    #                       'dob': dob, 'year_joined': 2003, 'parents': parents})
    #     student = Student.objects.get(last_name='Mowa')
    #     self.assertEqual(student.first_name, first_name)
    #     self.assertEqual(student.last_name, last_name)
    #     self.assertEqual(student.dob, datetime(*strptime(dob, '%Y-%m-%d')[:6]).date())
    #     self.assertEqual(student.year_joined, 2003)
    #     self.assertEqual(len(student.parent_fk_list), 1)
    #     p0 = Parent.objects.get(pk=student.parent_fk_list[0])
    #     self.assertEqual(p0.name, 'Nguetchuissi Richard')
    #     self.assertEqual(p0.phone, '690000000')
    #     self.assertEqual(p0.email, 'nguetch@yahoo.fr')
    #     self.assertEqual(p0.relation, 'Father')
    #
    # @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101',
    #                    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    # def test_ChangeStudent_with_existing_student(self):
    #     """
    #     Change must update Student information accordingly
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:change_student'))
    #     self.assertEqual(response.status_code, 200)
    #     first_name = u'Hervé'
    #     last_name = u'Siyou Kamgnie'
    #     dob = u'1987-03-31'
    #     p = [{'id': '', 'member_id': '', 'name': 'Makuate Bernadette',
    #           'phone': '699552147', 'email': 'bena@yahoo.fr', 'relation': 'Sister'},
    #          {'id': '574fb307c0cbed6b4f246a83', 'member_id': '56eb6d04b37b3379b531e014', 'name': '',
    #           'phone': '', 'email': '', 'relation': 'Mother'}]
    #     parents = json.dumps(p)
    #     self.client.post(reverse('school:change_student', args=('584f03a7bbd6b46a8fc0c242', )),
    #                      {'action': 'change', 'classroom': '60e011bd0b53137b33471d82',
    #                       'first_name': first_name, 'last_name': last_name,
    #                       'gender': 'Male', 'dob': dob, 'year_joined': 2003, 'parents': parents})
    #     student = Student.objects.get(pk='584f03a7bbd6b46a8fc0c242')
    #     self.assertEqual(student.first_name, first_name)
    #     self.assertEqual(student.last_name, last_name)
    #     self.assertEqual(student.dob, datetime(*strptime(dob, '%Y-%m-%d')[:6]).date())
    #     self.assertEqual(student.year_joined, 2003)
    #     self.assertEqual(len(student.parent_fk_list), 2)
    #     p0 = Parent.objects.get(pk=student.parent_fk_list[0])
    #     p1 = Parent.objects.get(pk=student.parent_fk_list[1])
    #     self.assertEqual(p0.name, 'Makuate Bernadette')
    #     self.assertEqual(p0.phone, '699552147')
    #     self.assertEqual(p0.email, 'bena@yahoo.fr')
    #     self.assertEqual(p0.relation, 'Sister')
    #     self.assertEqual(p1.relation, 'Mother')
    #
    # @override_settings(IKWEN_SERVICE_ID='56eb6d04b37b3379b531b101',
    #                    CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}})
    # def test_ChangeStudent_browse_tabs(self):
    #     """
    #     Tabs must be reachable
    #     """
    #     self.client.login(username='member2', password='admin')
    #     response = self.client.get(reverse('school:change_student'), {'tab': 'info'})
    #     self.assertEqual(response.status_code, 200)
    #     response = self.client.get(reverse('school:change_student'), {'tab': 'scores'})
    #     self.assertEqual(response.status_code, 200)
    #     response = self.client.get(reverse('school:change_student'), {'tab': 'accounting'})
    #     self.assertEqual(response.status_code, 200)
    #     response = self.client.get(reverse('school:change_student'), {'tab': 'accounting'})
    #     self.assertEqual(response.status_code, 200)
