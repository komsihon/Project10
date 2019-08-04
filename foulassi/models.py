from datetime import datetime

from django.conf import settings
from django.db import models
from django.template import Context
from django.template.loader import get_template
from django.utils.module_loading import import_by_path
from django.utils.translation import gettext_lazy as _
from django_mongodb_engine.contrib import MongoDBManager
from djangotoolbox.fields import ListField, EmbeddedModelField

from ikwen.accesscontrol.models import Member
from ikwen.core.constants import GENDER_CHOICES
from ikwen.core.utils import get_service_instance
from ikwen.core.models import Model, AbstractConfig, Service
from ikwen.core.fields import MultiImageField
from ikwen.theming.models import Theme
from ikwen.billing.models import AbstractInvoice, AbstractPayment

TEACHERS = "Teachers"
BEST_OF_ALL = "BestOfAll"
AVERAGE_OF_ALL = "AverageOfAll"

# Event types
ALL_SCORES_SET = "AllScoresSet"
LOW_EMAIL_CREDIT = "LowEmailCredit"
LOW_SMS_CREDIT = "LowSMSCredit"
REPORT_CARDS_GENERATED = "ReportCardsGenerated"
REPORT_CARDS_FAILED_TO_GENERATE = "ReportCardsFailedToGenerate"
PARENT_REQUEST_KID = "ParentRequestKid"


def get_school_year(request=None):
    if request:
        return request.session.get('school_year', get_school_year())
    now = datetime.now()
    month = now.month
    if 8 <= month <= 12:
        return now.year
    return now.year - 1


class Teacher(Model):
    member = models.ForeignKey(Member)
    school_year = models.IntegerField(default=get_school_year, db_index=True)

    def __unicode__(self):
        return self.member.full_name

    def get_classroom_list(self):
        from ikwen_foulassi.school.models import Classroom
        classroom_fk_list = set([])
        for obj in self.teacherresponsibility_set.all():
            classroom_fk_list = classroom_fk_list | set(obj.classroom_fk_list)
        for fk in classroom_fk_list:
            try:
                yield Classroom.objects.get(pk=fk)
            except:
                pass

    def get_subject_list(self, classroom):
        for obj in self.teacherresponsibility_set.all():
            if classroom.id in obj.classroom_fk_list:
                yield obj.subject


class Student(Model):
    UPLOAD_TO = 'foulassi/students'
    school = models.ForeignKey(Service, blank=True, null=True,
                               related_name='+', default=get_service_instance)
    registration_number = models.CharField(max_length=30, unique=True)
    first_name = models.CharField(max_length=100, db_index=True)
    last_name = models.CharField(max_length=100, db_index=True)
    gender = models.CharField(max_length=15, choices=GENDER_CHOICES, db_index=True)
    dob = models.DateField(_("Date of birth"))
    photo = MultiImageField(upload_to=UPLOAD_TO, blank=True, null=True,
                            max_size=600, small_size=200, thumb_size=100, editable=False)
    classroom = models.ForeignKey('school.Classroom')
    is_repeating = models.BooleanField(default=False)
    year_joined = models.IntegerField(default=get_school_year, db_index=True,
                                      help_text=_("Year when student joined this school"))
    score_history = ListField()
    school_year = models.IntegerField(default=get_school_year, db_index=True)
    is_confirmed = models.BooleanField(default=False)  # Confirmed student cannot be deleted again
    is_excluded = models.BooleanField(default=False)  # Excluded student does not appear in classroom student list
    tags = models.TextField(blank=True, null=True, db_index=True)
    kid_fees_paid = models.BooleanField(default=False,
                                        help_text="Whether a parent has ever paid to follow kid on the Kids platform.")

    def __unicode__(self):
        return self.last_name + ' ' + self.first_name

    def get_score_list(self, subject, using='default'):
        from ikwen_foulassi.school.models import Score
        return Score.objects.using(using).filter(student=self, subject=subject).order_by('session')


class Parent(Model):
    """
    Parent of a Student. Can either be a newly created object
    or can point to an ikwen.Member
    """
    student = models.ForeignKey(Student)
    member = models.ForeignKey(Member, blank=True, null=True,
                               db_index=False)  # Create index manually in production, setting it to False make unit tests work
    name = models.CharField(max_length=100, blank=True, null=True, db_index=True,
                            help_text=_("Full name of the person"))
    phone = models.CharField(max_length=30, blank=True, null=True, db_index=True)
    email = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    relation = models.CharField(max_length=30, db_index=True,
                                help_text=_("Relationship that links the person to the student"))

    def get_name(self):
        if self.member:
            return self.member.full_name
        return self.name

    def get_phone(self):
        if self.member:
            return self.member.phone
        return self.phone

    def get_email(self):
        if self.member:
            return self.member.email
        return self.email

    def __unicode__(self):
        return self.name


class ParentProfile(Model):
    member = models.ForeignKey(Member)
    student_list = ListField(EmbeddedModelField('Student'))


class StudentsPopulation(models.Model):
    girls_count = models.IntegerField(default=0)
    boys_count = models.IntegerField(default=0)
    school_year = models.IntegerField(default=get_school_year, db_index=True)

    def _get_student_count(self):
        return self.girls_count + self.boys_count
    student_count = property(_get_student_count)

    class Meta:
        abstract = True


class ResultsTracker(StudentsPopulation):
    girls_participation_history = ListField()
    girls_highest_score_history = ListField(EmbeddedModelField('school.Score'))
    girls_lowest_score_history = ListField(EmbeddedModelField('school.Score'))
    girls_avg_score_history = ListField()
    girls_success_history = ListField()

    boys_participation_history = ListField()
    boys_highest_score_history = ListField(EmbeddedModelField('school.Score'))
    boys_lowest_score_history = ListField(EmbeddedModelField('school.Score'))
    boys_avg_score_history = ListField()
    boys_success_history = ListField()

    class Meta:
        abstract = True

    def _get_participation_history(self):
        return [sum(x) for x in zip(self.girls_participation_history, self.boys_participation_history)]
    participation_history = property(_get_participation_history)

    def _get_highest_score_history(self):
        return [max(x) for x in zip(self.girls_highest_score_history, self.boys_highest_score_history)]
    highest_score_history = property(_get_highest_score_history)

    def _get_lowest_score_history(self):
        return [min(x) for x in zip(self.girls_lowest_score_history, self.boys_lowest_score_history)]
    lowest_score_history = property(_get_lowest_score_history)

    def _get_avg_score_history(self):
        return [sum(x)/2 for x in zip(self.girls_avg_score_history, self.boys_avg_score_history)]
    avg_score_history = property(_get_avg_score_history)

    def _get_success_history(self):
        return [sum(x) for x in zip(self.girls_success_history, self.boys_success_history)]
    success_history = property(_get_success_history)

    def _get_boys_success_percent_history(self):
        return [float(x[0] * 100)/x[1] for x in zip(self.boys_success_history, self.boys_participation_history)]
    boys_success_percent_history = property(_get_boys_success_percent_history)

    def _get_girls_success_percent_history(self):
        return [float(x[0] * 100)/x[1] for x in zip(self.girls_success_history, self.girls_participation_history)]
    girls_success_percent_history = property(_get_girls_success_percent_history)

    def _get_success_percent_history(self):
        return [float(sum(x[:-1]) * 100)/x[-1]
                for x in zip(self.girls_success_history, self.boys_success_history, self.participation_history)]
    success_percent_history = property(_get_success_percent_history)


class DisciplineTracker(StudentsPopulation):
    girls_history = ListField()
    boys_history = ListField()
    total_history = ListField()

    class Meta:
        abstract = True


class SchoolConfig(AbstractConfig, ResultsTracker):
    SESSION_AVG_CALCULATION_CHOICES = (
        (AVERAGE_OF_ALL, _("Average of sessions'scores")),
        (BEST_OF_ALL, _("Best score of all sessions"))
    )
    theme = models.ForeignKey(Theme, blank=True, null=True)
    back_to_school_date = models.DateTimeField(blank=True, null=True)
    registration_fees_title = models.CharField(max_length=60, default=_("Registration fees"))
    registration_fees_deadline = models.DateField(blank=True, null=True)
    first_instalment_title = models.CharField(max_length=60, default=_("First instalment"))
    first_instalment_deadline = models.DateField(blank=True, null=True)
    second_instalment_title = models.CharField(max_length=60, default=_("Second instalment"))
    second_instalment_deadline = models.DateField(blank=True, null=True)
    third_instalment_title = models.CharField(max_length=60, default=_("Third instalment"))
    third_instalment_deadline = models.DateField(blank=True, null=True)
    session_group_avg = models.CharField(max_length=60, choices=SESSION_AVG_CALCULATION_CHOICES, default=AVERAGE_OF_ALL,
                                         help_text=_("Method of calculation of Term score. Average of sessions "
                                                     "scores or best score of all sessions."))
    is_public = models.BooleanField(default=False,
                                    help_text="Designates whether this school is a State school.")

    def save(self, *args, **kwargs):
        bts = self.back_to_school_date
        # if bts.hour != 7 or bts.min != 30:
        if bts and (bts.hour != 7 or bts.min != 30):
            # Always set back to school time to 07:30 AM
            self.back_to_school_date = datetime(bts.year, bts.month, bts.day, 7, 30)
        super(SchoolConfig, self).save(*args, **kwargs)


class Invoice(AbstractInvoice):
    student = models.ForeignKey(Student, blank=True, null=True)
    school_year = models.IntegerField(default=get_school_year, db_index=True)
    is_tuition = models.BooleanField(default=False)

    def get_title(self):
        return ', '.join([entry.item.label for entry in self.entries])


class Payment(AbstractPayment):
    invoice = models.ForeignKey(Invoice)


class KidRequest(Model):
    """
    A request to follow one ore more children, issued by a parent
    """
    parent = models.ForeignKey(Member)
    kids_details = models.TextField(blank=True, null=True)


class EventType(Model):
    UPLOAD_TO = 'event_icons'
    codename = models.CharField(max_length=60)
    icon = models.ImageField(upload_to=UPLOAD_TO)
    renderer = models.CharField(max_length=100)


class Event(Model):
    type = models.ForeignKey(EventType)
    object_id_list = ListField()
    is_processed = models.BooleanField(default=False,
                                       help_text="Designates whether user applied necessary "
                                                 "actions for this event if any.")
    objects = MongoDBManager()

    def render(self, request=None):
        renderer = import_by_path(self.type.renderer)
        if getattr(settings, 'DEBUG', False):
            return renderer(self, request)
        else:
            try:
                return renderer(self, request)
            except:
                template_name = 'foulassi/events/rendering_error.html'
                html_template = get_template(template_name)
                return html_template.render(Context({}))
