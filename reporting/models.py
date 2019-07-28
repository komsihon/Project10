from django.db import models
from djangotoolbox.fields import ListField
from ikwen.core.models import Model, AbstractWatchModel, Service
from ikwen.core.constants import MALE, FEMALE
from ikwen.accesscontrol.models import Member
from ikwen_foulassi.foulassi.models import Student, ResultsTracker, DisciplineTracker, get_school_year
from ikwen_foulassi.school.models import Classroom, Subject, Level, Session, Lesson, SessionGroup, DisciplineItem, \
    Score, SessionGroupScore


class LessonReport(AbstractWatchModel):
    subject = models.ForeignKey(Subject)
    level = models.ForeignKey(Level, null=True)
    classroom = models.ForeignKey(Classroom, null=True)
    school_year = models.IntegerField(default=get_school_year)
    count_history = ListField()
    hours_count_history = ListField()

    total_count = models.IntegerField(default=0)
    total_hours_count = models.IntegerField(default=0)

    class Meta:
        unique_together = ('level', 'classroom', 'subject')


class DisciplineReport(AbstractWatchModel, DisciplineTracker):
    discipline_item = models.ForeignKey(DisciplineItem)
    level = models.ForeignKey(Level, null=True)
    classroom = models.ForeignKey(Classroom, null=True)

    class Meta:
        unique_together = ('level', 'classroom', 'discipline_item')


class StudentDisciplineReport(AbstractWatchModel):
    student = models.ForeignKey(Student)
    discipline_item = models.ForeignKey(DisciplineItem)
    count_history = ListField()
    total_count = models.IntegerField(default=0)
    last_add_on = models.DateTimeField(blank=True, null=True, db_index=True)

    class Meta:
        unique_together = ('student', 'discipline_item')


class SessionReport(Model, ResultsTracker):
    subject = models.ForeignKey(Subject, null=True)
    classroom = models.ForeignKey(Classroom, null=True)
    level = models.ForeignKey(Level, null=True)

    class Meta:
        unique_together = ('level', 'classroom', 'subject')

    def get_students_having_score(self, value):
        student_list = [score.student
                        for score in Score.objects.select_related('student').
                            filter(session=self.session, subject=self.subject, value=value)]
        return student_list

    def get_boys_having_score(self, value):
        student_list = self.get_students_having_score(value)
        boys_list = [student for student in student_list if student.gender == MALE]
        return boys_list

    def get_girls_having_score(self, value):
        student_list = self.get_students_having_score(value)
        girls_list = [student for student in student_list if student.gender == FEMALE]
        return girls_list


class SessionGroupReport(Model, ResultsTracker):
    subject = models.ForeignKey(Subject, null=True)
    classroom = models.ForeignKey(Classroom, null=True)
    level = models.ForeignKey(Level, null=True)

    class Meta:
        unique_together = ('level', 'classroom', 'subject')

    def get_students_having_score(self, value):
        student_list = [score.student
                        for score in SessionGroupScore.objects.select_related('student').
                            filter(session_group=self.session_group, subject=self.subject, value=value)]
        return student_list

    def get_boys_having_score(self, value):
        student_list = self.get_students_having_score(value)
        boys_list = [student for student in student_list if student.gender == MALE]
        return boys_list

    def get_girls_having_score(self, value):
        student_list = self.get_students_having_score(value)
        girls_list = [student for student in student_list if student.gender == FEMALE]
        return girls_list


class YearReport(Model, ResultsTracker):
    subject = models.ForeignKey(Subject, null=True)
    classroom = models.ForeignKey(Classroom, null=True)
    level = models.ForeignKey(Level, null=True)

    class Meta:
        unique_together = ('level', 'classroom', 'subject')


class ReportCardBatch(Model):
    # service = models.ForeignKey(Service)
    member = models.ForeignKey(Member)
    session = models.ForeignKey(Session, blank=True, null=True)
    session_group = models.ForeignKey(SessionGroup, blank=True, null=True)
    generated = models.IntegerField(default=0)
    total = models.IntegerField()
    duration = models.IntegerField(default=0)
    message = models.TextField(blank=True, null=True)
