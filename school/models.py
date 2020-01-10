from datetime import datetime

from django.core.exceptions import MultipleObjectsReturned
from django.db import models
from django_mongodb_engine.contrib import MongoDBManager
from djangotoolbox.fields import ListField, EmbeddedModelField
from ikwen.accesscontrol.models import Member
from ikwen.core.models import Model
from django.utils.translation import gettext_lazy as _
from ikwen_foulassi.foulassi.models import Student, Teacher, ResultsTracker, get_school_year


# ikwen Events
STUDENT_EXCLUDED = "StudentExcluded"


class Level(Model, ResultsTracker):
    """
    A school level
    """
    name = models.CharField(_("Name"), max_length=30,
                            help_text=_("<strong>Eg:</strong> Form1, Form2, ..."))
    slug = models.SlugField()
    registration_fees = models.IntegerField(_("Registration fees"), default=0)
    first_instalment = models.IntegerField(_("First instalment"), default=0)
    second_instalment = models.IntegerField(_("Second instalment"), default=0)
    third_instalment = models.IntegerField(_("Third instalment"), default=0)
    order_of_appearance = models.IntegerField(default=0)
    subject_coefficient_list = ListField(EmbeddedModelField('SubjectCoefficient'))

    class Meta:
        unique_together = (
            ('name', 'school_year'),
            ('slug', 'school_year'),
        )
        ordering = ('order_of_appearance', 'name')

    def __unicode__(self):
        return self.name


class Classroom(Model, ResultsTracker):
    level = models.ForeignKey(Level, verbose_name=_("Level"))
    name = models.CharField(_("Name"), max_length=30,
                            help_text=_("Raw name of the class. Don't write the level again. <br>Eg: A, B ... "
                                        "The level will be added to get the full name."))
    slug = models.SlugField()
    registration_fees = models.IntegerField(_("Registration fees"), default=0)
    first_instalment = models.IntegerField(_("First instalment"), default=0)
    second_instalment = models.IntegerField(_("Second instalment"), default=0)
    third_instalment = models.IntegerField(_("Third instalment"), default=0)
    professor = models.ForeignKey(Teacher, verbose_name=_("Professor"), blank=True, null=True)
    leader = models.ForeignKey(Student, related_name='leaders', blank=True, null=True)
    subject_coefficient_list = ListField(EmbeddedModelField('SubjectCoefficient'))

    class Meta:
        unique_together = ('level', 'name', 'school_year')
        ordering = ('level', 'name')
        permissions = (
            ("ik_access_scores", "Can view and edit student scores"),
        )

    def __unicode__(self):
        return str(self.level).decode('utf8') + ' ' + self.name

    def __cmp__(self, other):
        if self.name == other.name:
            return 0
        return 1 if self.name > other.name else -1

    def _get_size(self):
        return self.student_count
    size = property(_get_size)


class Subject(Model):
    name = models.CharField(_("Name"), max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    is_visible = models.BooleanField(default=True)

    class Meta:
        ordering = ('name', )

    def __unicode__(self):
        return self.name

    def get_teacher(self, classroom):
        responsibilities = TeacherResponsibility.objects\
            .raw_query({'classroom_fk_list': {'$elemMatch': {'$eq': classroom.id}}})\
            .select_related('teacher').filter(subject=self)
        try:
            return responsibilities[0].teacher
        except:
            pass

    def set_teacher(self, classroom, teacher):
        responsibility, update = TeacherResponsibility.objects.get_or_create(teacher=teacher, subject=self)
        if classroom.id not in responsibility.classroom_fk_list:
            responsibility.classroom_fk_list.append(classroom.id)
        responsibility.save()


class SubjectCoefficient(models.Model):
    subject = models.ForeignKey(Subject)
    group = models.IntegerField(default=0)
    coefficient = models.IntegerField(default=1)
    lessons_due = models.IntegerField(default=0)
    hours_due = models.IntegerField(default=0)

    def __cmp__(self, other):
        self_subject = self.subject  # Avoids multiple database queries
        other_subject = other.subject

        if self.group == other.group:
            if self_subject.name == other_subject.name:
                return 0
            return 1 if self_subject.name > other_subject.name else -1
        return 1 if self.group > other.group else -1


class TeacherResponsibility(Model):
    teacher = models.ForeignKey(Teacher)
    subject = models.ForeignKey(Subject)
    classroom_fk_list = ListField()

    objects = MongoDBManager()

    class Meta:
        unique_together = ('teacher', 'subject', )


def get_subject_list(obj, using='default'):
    """
    Gets a list of Subject of classes having the field
    subject_coefficient_list: Level and Classroom
    Every Subject in the returned list has additional fields
    group, coefficient, lessons_due, and hours_due for easy access to them
    """
    subject_list = []
    for item in obj.subject_coefficient_list:
        try:
            subject = Subject.objects.using(using).get(pk=item.__dict__['subject_id'])
            subject.group = item.group
            subject.coefficient = item.coefficient
            subject.lessons_due = item.lessons_due
            subject.hours_due = item.hours_due
            subject_list.append(subject)
        except Subject.DoesNotExist:
            obj.subject_coefficient_list.remove(item)
    obj.save(using=using)
    return subject_list


# def clean_subject_list(obj):
#     """
#     Goes through a list of Subject of classes having the field
#     subject_list: Level and Classroom and removes unexisting Subject
#     """
#     for item in obj.subject_list:
#         try:
#             item.subject
#         except Subject.DoesNotExist:
#             obj.subject_list.remove(item)
#     obj.save()


class SessionGroup(Model, ResultsTracker):
    """
    A group of exam sessions (Term, Semester, ...)
    """
    name = models.CharField(_("Name"), max_length=60)
    slug = models.SlugField(blank=True, null=True)
    starts_on = models.DateField(_("Starts on"), default=datetime.now)
    ends_on = models.DateField(_("Ends on"), default=datetime.now)

    class Meta:
        ordering = ('id', 'name', )
        unique_together = ('name', 'school_year', )

    def __unicode__(self):
        return self.name

    def _get_order_number(self):
        all_sessions = list(SessionGroup.objects.filter(school_year=get_school_year()))
        return all_sessions.index(self)
    order_number = property(_get_order_number)

    def get_obj_details(self):
        return self.starts_on.strftime('%Y, %m/%d') + ' - ' + self.ends_on.strftime('%Y, %m/%d')


class Session(Model, ResultsTracker):
    """
    An examination session
    """
    name = models.CharField(_("Name"), max_length=60)
    slug = models.SlugField(blank=True, null=True)
    session_group = models.ForeignKey(SessionGroup, verbose_name=_("Session group"), blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_current = models.BooleanField(default=False)
    all_scores_set_on = models.DateTimeField(blank=True, null=True)
    report_cards_generated_on = models.DateTimeField(blank=True, null=True)
    starts_on = models.DateField(default=datetime.now)
    ends_on = models.DateField(default=datetime.now)

    class Meta:
        ordering = ('id', )
        unique_together = ('name', 'school_year')

    def __unicode__(self):
        return u"%s: %s" % (self.session_group.name, self.name)

    def _get_order_number(self):
        all_sessions = list(Session.objects.filter(school_year=get_school_year()))
        return all_sessions.index(self)
    order_number = property(_get_order_number)

    def get_obj_details(self):
        return self.starts_on.strftime('%Y, %m/%d') + ' - ' + self.ends_on.strftime('%Y, %m/%d')

    @staticmethod
    def get_current():
        try:
            session = Session.objects.get(is_current=True)
        except Session.DoesNotExist:
            try:
                session = Session.objects.filter(school_year=get_school_year())[0]
                session.is_current = True
                session.save()
            except IndexError:
                return None
        except MultipleObjectsReturned:
            session = Session.objects.filter(is_current=True).order_by('-id')[0]
            Session.objects.exclude(pk=session.id).update(is_current=False)
        return session


class Lesson(Model):
    """
    Lesson taught by a teacher in a Classroom session
    """
    classroom = models.ForeignKey(Classroom, verbose_name=_("Classroom"))
    subject = models.ForeignKey(Subject, verbose_name=_("Subject"))
    teacher = models.ForeignKey(Teacher, verbose_name=_("Teacher"))
    title = models.CharField(_("Title"), max_length=150, blank=True, null=True)
    hours_count = models.IntegerField()
    is_complete = models.BooleanField(default=False)
    school_year = models.IntegerField(default=get_school_year, db_index=True)


class AbstractScore(Model):
    subject = models.ForeignKey(Subject, null=True)
    student = models.ForeignKey(Student)
    value = models.FloatField(blank=True, null=True)
    rank = models.IntegerField(blank=True, null=True)
    was_viewed = models.BooleanField(default=False,
                                     help_text="True if parent already viewed this.")

    class Meta:
        abstract = True

    def __cmp__(self, other):
        if self.value == other.value:
            return 0
        return 1 if self.value > other.value else -1


class Score(AbstractScore):
    session = models.ForeignKey(Session)

    class Meta:
        unique_together = ('session', 'subject', 'student', )
        ordering = ('value', )


class SessionGroupScore(AbstractScore):
    session_group = models.ForeignKey(SessionGroup)
    value1 = models.FloatField(blank=True, null=True)  # Value of the first session
    value2 = models.FloatField(blank=True, null=True)  # Value of the second session

    class Meta:
        unique_together = ('session_group', 'subject', 'student', )
        ordering = ('value', )


class ScoreUpdateRequest(Model):
    session = models.ForeignKey(Session)
    subject = models.ForeignKey(Subject)
    classroom = models.ForeignKey(Classroom)
    member = models.ForeignKey(Member)
    update_list = ListField(EmbeddedModelField('Score'))


class DisciplineItem(Model):
    ABSENCE = 'absence'
    LATENESS = 'lateness'
    WARNING = 'warning'
    CENSURE = 'censure'
    PARENT_CONVOCATION = 'parent-convocation'
    TEMPORARY_EXCLUSION = 'temporary-exclusion'
    EXCLUSION = 'exclusion'
    name = models.CharField(_("Title"), max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    unit = models.CharField(_("Unit"), max_length=15, blank=True, null=True)
    editable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    has_count = models.BooleanField(_("With counter ?"), default=True)

    def __unicode__(self):
        return self.name


class DisciplineLogEntry(Model):
    item = models.ForeignKey(DisciplineItem)
    student = models.ForeignKey(Student)
    details = models.CharField(max_length=150, blank=True, null=True)
    count = models.FloatField()
    happened_on = models.DateTimeField(blank=True, null=True, db_index=True)
    is_justified = models.BooleanField(default=False)
    was_viewed = models.BooleanField(default=False,
                                     help_text="True if parent already viewed this.")

    class Meta:
        ordering = ('-id', )

    def to_dict(self):
        var = super(DisciplineLogEntry, self).to_dict()
        var['item'] = self.item.to_dict()
        return var


class Justificatory(Model):
    UPLOAD_TO = 'foulassi/justificatories'
    entry = models.OneToOneField(DisciplineLogEntry)
    details = models.CharField(max_length=150, blank=True, null=True)
    image = models.ImageField(upload_to=UPLOAD_TO, blank=True, null=True)

    def __unicode__(self):
        return self.details[:30]
