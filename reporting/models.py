from django.conf import settings
from django.db import models
from djangotoolbox.fields import ListField
from django.utils.translation import gettext_lazy as _
from ikwen.core.models import Model, AbstractWatchModel
from ikwen.core.constants import MALE, FEMALE
from ikwen.accesscontrol.models import Member
from ikwen_foulassi.foulassi.models import Student, ResultsTracker, DisciplineTracker, get_school_year
from ikwen_foulassi.school.models import Classroom, Subject, Level, Session, SessionGroup, DisciplineItem, \
    Score, SessionGroupScore


class ReportCardHeader(Model):
    UPLOAD_TO = 'report_card_header/'
    country_name = models.CharField(_("Country name"), max_length=150)
    country_moto = models.CharField(_("Country moto"), max_length=150)
    head_organization = models.CharField(_("Head organization"), max_length=250)
    head_organization_logo = models.ImageField(_("Head organization logo"), upload_to=UPLOAD_TO,
                                               help_text=_("500 x 500px; will appear on Report Card"))
    lang = models.CharField(_("Language"), max_length=10, choices=getattr(settings, 'LANGUAGES'), default='en')

    def __unicode__(self):
        return self.country_name + ' | ' + self.lang

    def get_obj_details(self):
        return self.country_moto


class LessonReport(AbstractWatchModel):
    subject = models.ForeignKey(Subject, null=True)
    level = models.ForeignKey(Level, null=True)
    classroom = models.ForeignKey(Classroom, null=True)
    school_year = models.IntegerField(default=get_school_year)
    count_history = ListField()
    hours_count_history = ListField()

    total_count = models.IntegerField(default=0)
    total_hours_count = models.IntegerField(default=0)

    class Meta:
        unique_together = ('level', 'classroom', 'subject', 'school_year')


class DisciplineReport(AbstractWatchModel, DisciplineTracker):
    discipline_item = models.ForeignKey(DisciplineItem)
    level = models.ForeignKey(Level, null=True)
    classroom = models.ForeignKey(Classroom, null=True)

    class Meta:
        unique_together = ('level', 'classroom', 'discipline_item', 'school_year')


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
        unique_together = ('level', 'classroom', 'subject', 'school_year')

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
        unique_together = ('level', 'classroom', 'subject', 'school_year')

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
        unique_together = ('level', 'classroom', 'subject', 'school_year')


class ReportCardBatch(Model):
    # service = models.ForeignKey(Service)
    member = models.ForeignKey(Member)
    session = models.ForeignKey(Session, blank=True, null=True)
    session_group = models.ForeignKey(SessionGroup, blank=True, null=True)
    generated = models.IntegerField(default=0)
    total = models.IntegerField()
    duration = models.IntegerField(default=0)
    message = models.TextField(blank=True, null=True)
