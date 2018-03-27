from django.db import models
from django.utils.translation import gettext_lazy as _
from djangotoolbox.fields import ListField, EmbeddedModelField
from ikwen.accesscontrol.models import Member
from ikwen.core.constants import GENDER_CHOICES
from ikwen.core.models import Model, AbstractConfig
from ikwen.core.fields import MultiImageField


class Teacher(Model):
    member = models.OneToOneField(Member)
    classroom_fk_list = ListField()
    responsibilities = ListField(EmbeddedModelField('school.TeacherResponsibility'))


class Parent(Model):
    """
    Parent of a Student. Can either be a newly created object
    or can point to an ikwen.Member
    """
    member = models.ForeignKey(Member, blank=True, null=True,
                               db_index=False)  # Create index manually in production, setting it to False make unit tests work
    name = models.CharField(max_length=100, blank=True, null=True,
                            help_text=_("Full name of the person"))
    phone = models.CharField(max_length=30, blank=True, null=True)
    email = models.CharField(max_length=100, blank=True, null=True)
    relation = models.CharField(max_length=30,
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


class Student(Model):
    PHOTOS_FOLDER = 'school/students'
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=15, blank=True, null=True, choices=GENDER_CHOICES)
    dob = models.DateField(blank=True, null=True)
    photo = MultiImageField(upload_to=PHOTOS_FOLDER, blank=True, null=True,
                            max_size=600, small_size=200, thumb_size=100)
    classroom = models.ForeignKey('school.Classroom')
    is_repeating = models.BooleanField(default=False)
    is_leader = models.BooleanField(default=False)
    year_joined = models.IntegerField(help_text=_("Year when student joined this school"), blank=True, null=True)
    score_history = ListField()
    parent_fk_list = ListField(help_text="Parents as a list foreign keys of Parent objects")

    def get_parents(self):
        parents = []
        for fk in self.parent_fk_list:
            try:
                parents.append(Parent.objects.get(pk=fk))
            except:
                pass
        return parents


class StudentsPopulation(models.Model):
    girls_count = models.IntegerField(default=0)
    boys_count = models.IntegerField(default=0)

    def _get_students_count(self):
        return self.girls_count + self.boys_count
    students_count = property(_get_students_count)

    class Meta:
        abstract = True


class ResultsTracker(StudentsPopulation):
    girls_participation_history = ListField()
    girls_highest_score_history = ListField()
    girls_lowest_score_history = ListField()
    girls_avg_score_history = ListField()
    girls_success_history = ListField()

    boys_participation_history = ListField()
    boys_highest_score_history = ListField()
    boys_lowest_score_history = ListField()
    boys_avg_score_history = ListField()
    boys_success_history = ListField()

    class Meta:
        abstract = True


class School(AbstractConfig, ResultsTracker):
    registration_fees = models.IntegerField(default=0)
