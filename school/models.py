from django.db import models
from djangotoolbox.fields import ListField
from ikwen.accesscontrol.models import Member
from ikwen.core.models import Model
from ikwen_foulassi.foulassi.models import Student, Teacher, ResultsTracker


class Level(Model, ResultsTracker):
    """
    A school level
    """
    name = models.CharField(max_length=30, unique=True)
    tuition_fees = models.IntegerField(default=0)
    order_of_appearance = models.IntegerField(default=0)
    subject_fk_list = ListField()

    class Meta:
        ordering = ('order_of_appearance', 'name')


class Classroom(Model, ResultsTracker):
    level = models.ForeignKey(Level)
    name = models.CharField(max_length=30)
    tuition_fees = models.IntegerField(default=0)
    professor = models.ForeignKey(Teacher, blank=True, null=True)
    subject_fk_list = ListField()

    class Meta:
        ordering = ('level', 'name')

    def get_leader(self):
        try:
            return Student.objects.get(classroom=self, is_leader=True)
        except:
            pass


class TeacherResponsibility(Model):
    classroom = models.ForeignKey(Classroom)
    subject_fk_list = ListField()


class Subject(Model):
    name = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ('name', )


class Session(Model, ResultsTracker):
    """
    An examination session
    """
    name = models.CharField(max_length=60)

    def _get_order_number(self):
        all_sessions = list(Session.objects.all())
        return all_sessions.index(self)
    order_number = property(_get_order_number)


class SubjectSession(Model, ResultsTracker):
    """
    An examination session for a single Subject
    """
    subject = models.ForeignKey(Subject)
    session = models.ForeignKey(Session)
    classroom = models.ForeignKey(Classroom, null=True)
    level = models.ForeignKey(Level, null=True)

    class Meta:
        unique_together = ('subject', 'session', 'classroom')


class ScoreBase(Model):
    student = models.ForeignKey(Student)
    value = models.FloatField()

    class Meta:
        abstract = True


class Score(ScoreBase):
    session = models.ForeignKey(Session)
    subject = models.ForeignKey(Subject, null=True)

    class Meta:
        ordering = ('value', )


class ScoreUpdateRequest(Model):
    session = models.ForeignKey(Session)
    subject = models.ForeignKey(Subject)
    classroom = models.ForeignKey(Classroom)
    member = models.ForeignKey(Member)
    update_list = ListField()


def get_subject_list(obj):
    """
    Gets a list of Subject objects of classes
    having the field subject_fk_list: Level and Classroom
    """
    subject_list = []
    for fk in obj.subject_fk_list:
        try:
            subject = Subject.objects.get(pk=fk)
            subject_list.append(subject)
        except Subject.DoesNotExist:
            pass
    return subject_list
