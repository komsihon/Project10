import json

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import TemplateView
from ikwen.accesscontrol.models import Member
from ikwen.core.utils import get_model_admin_instance
from ikwen.core.views import HybridListView, ChangeObjectBase
from ikwen_foulassi.foulassi.models import TEACHERS, Teacher, get_school_year, Student, Event
from ikwen_foulassi.school.admin import LevelAdmin, SubjectAdmin, SessionGroupAdmin, SessionAdmin, DisciplineItemAdmin
from ikwen_foulassi.school.models import Level, Session, Subject, DisciplineItem, TeacherResponsibility, Classroom, \
    get_subject_list, SubjectCoefficient, SessionGroup, Score
from permission_backend_nonrel.models import UserPermissionList


class LevelList(HybridListView):
    model = Level
    template_name = 'school/level_list.html'

    def get_queryset(self):
        return Level.objects.filter(school_year=get_school_year(self.request))

    def get_context_data(self, **kwargs):
        context = super(LevelList, self).get_context_data(**kwargs)
        context['subject_list'] = Subject.objects.all()
        return context


class ChangeLevel(ChangeObjectBase):
    template_name = 'school/change_level.html'
    model = Level
    model_admin = LevelAdmin

    def get_context_data(self, **kwargs):
        context = super(ChangeLevel, self).get_context_data(**kwargs)
        level = context[self.context_object_name]
        level_subject_list = []
        if level:
            level_subject_list = get_subject_list(level)
            if not level_subject_list:
                level_subject_list = get_subject_list(level)
        subject_list = []
        for subject in Subject.objects.all():
            try:
                index = level_subject_list.index(subject)
                subject.is_active = True
                subject.group = level_subject_list[index].group
                subject.coefficient = level_subject_list[index].coefficient
                subject.lessons_due = level_subject_list[index].lessons_due
                subject.hours_due = level_subject_list[index].hours_due
            except:
                pass
            subject_list.append(subject)
        context['subject_list'] = subject_list
        context['range_1_4'] = range(1, 4)
        return context

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        object_id = kwargs.get('object_id')
        if object_id:
            obj = get_object_or_404(self.model, pk=object_id)
        else:
            obj = self.model()
        object_admin = get_model_admin_instance(self.model, self.model_admin)
        ModelForm = object_admin.get_form(request)
        form = ModelForm(request.POST, instance=obj)
        if form.is_valid():
            obj.name = form.cleaned_data['name']
            obj.tuition_fees = form.cleaned_data['tuition_fees']
            item_list = request.POST['subjects'].split(',')
            subject_coefficient_list = []
            for item in item_list:
                tk = item.split(':')
                subject = Subject.objects.get(pk=tk[0])
                subject_coefficient = SubjectCoefficient(subject=subject, group=int(tk[1]), coefficient=int(tk[2]),
                                                         lessons_due=int(tk[3]), hours_due=int(tk[4]))
                subject_coefficient_list.append(subject_coefficient)
            obj.subject_coefficient_list = subject_coefficient_list
            obj.save()
            next_url = self.get_object_list_url(request, obj)
            if object_id:
                notice = obj._meta.verbose_name.capitalize() + ' <strong>' + str(obj).decode('utf8') + '</strong> ' + _('successfully updated')
            else:
                notice = obj._meta.verbose_name.capitalize() + ' <strong>' + str(obj).decode('utf8') + '</strong> ' + _('successfully created')
            messages.success(request, notice)
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)


class SubjectList(HybridListView):
    queryset = Subject.objects.filter(is_visible=True)


class ChangeSubject(ChangeObjectBase):
    model = Subject
    model_admin = SubjectAdmin


class SessionList(HybridListView):
    model = Session
    ordering = ('id', )

    def get_queryset(self):
        return Session.objects.filter(school_year=get_school_year(self.request))


class SessionGroupList(HybridListView):
    model = Session
    ordering = ('id', )

    def get_queryset(self):
        return SessionGroup.objects.filter(school_year=get_school_year(self.request))


class ChangeSession(ChangeObjectBase):
    model = Session
    model_admin = SessionAdmin


class ChangeSessionGroup(ChangeObjectBase):
    model = SessionGroup
    model_admin = SessionGroupAdmin


class DisciplineItemList(HybridListView):
    queryset = DisciplineItem.objects.filter(editable=True)


class ChangeDisciplineItem(ChangeObjectBase):
    model = DisciplineItem
    model_admin = DisciplineItemAdmin


class TeacherList(HybridListView):
    template_name = 'school/teacher_list.html'
    context_object_name = 'teacher_nonrel_perm_list'

    def get_queryset(self):
        group_id = Group.objects.get(name=TEACHERS).id
        return UserPermissionList.objects.raw_query({'group_fk_list': {'$elemMatch': {'$eq': group_id}}})

    def get_context_data(self, **kwargs):
        context = super(TeacherList, self).get_context_data(**kwargs)
        context['verbose_name'] = _('Teacher')
        context['verbose_name_plural'] = _('Teachers')
        return context


class TeacherDetail(TemplateView):
    model = Member
    template_name = 'school/teacher_detail.html'
    context_object_name = 'teacher'

    def get_context_data(self, **kwargs):
        context = super(TeacherDetail, self).get_context_data(**kwargs)
        object_id = kwargs['object_id']
        member = get_object_or_404(Member, pk=object_id)
        school_year = get_school_year(self.request)
        teacher = Teacher.objects.get(member=member, school_year=school_year)
        teacher_subject_list = [obj.subject for obj in teacher.teacherresponsibility_set.all()]
        subject_level_classroom_list = []
        for subject in teacher_subject_list:
            level_classroom_list = []
            classroom_fk_list = TeacherResponsibility.objects.get(teacher=teacher, subject=subject).classroom_fk_list
            for level in Level.objects.filter(school_year=school_year).order_by('order_of_appearance', 'name'):
                classroom_list = []
                for classroom in Classroom.objects.filter(level=level):
                    if classroom.id in classroom_fk_list:
                        classroom.is_active = True
                    current_teacher = subject.get_teacher(classroom)
                    if current_teacher and current_teacher != teacher:
                        classroom.is_assigned = True
                    classroom_list.append(classroom)
                obj = {
                    "name": level.name,
                    "classroom_list": classroom_list
                }
                level_classroom_list.append(obj)
            sub = {
                "id": subject.id,
                "name": subject.name,
                "level_classroom_list": level_classroom_list
            }
            subject_level_classroom_list.append(sub)

        level_classroom_list = []
        for level in Level.objects.filter(school_year=school_year).order_by('order_of_appearance', 'name'):
            obj = {
                "name": level.name,
                "classroom_list": Classroom.objects.filter(level=level)
            }
            level_classroom_list.append(obj)
        context['teacher'] = teacher
        context['subject_level_classroom_list'] = subject_level_classroom_list
        context['level_classroom_list'] = level_classroom_list
        context['teacher_subject_list'] = teacher_subject_list
        context['subject_list'] = Subject.objects.exclude(pk__in=[obj.id for obj in teacher_subject_list], is_visible=False)
        context['verbose_name'] = _('Teacher')
        context['verbose_name_plural'] = _('Teachers')
        return context

    def get(self, request, *args, **kwargs):
        action = self.request.GET.get('action')
        object_id = kwargs['object_id']
        member = get_object_or_404(Member, pk=object_id)
        teacher, update = Teacher.objects.get_or_create(member=member, school_year=get_school_year())
        if action == 'add_subject':
            return self.add_subject(self.request, teacher)
        elif action == 'save_responsibilities':
            return self.save_responsibilities(self.request, teacher)
        return super(TeacherDetail, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        action = request.GET.get('action')
        context = self.get_context_data(**kwargs)
        teacher = context['teacher']
        if action == 'save_responsibilities':
            return self.save_responsibilities(self.request, teacher)
        return render(request, self.template_name, context)

    def add_subject(self, request, teacher):
        try:
            subject_id = request.GET['subject_id']
            subject = Subject.objects.get(pk=subject_id)
            TeacherResponsibility.objects.get_or_create(teacher=teacher, subject=subject)
            level_classroom_list = []
            school_year = get_school_year()
            for level in Level.objects.filter(school_year=school_year).order_by('order_of_appearance', 'name'):
                classroom_list = []
                for classroom in Classroom.objects.filter(level=level):
                    if subject.get_teacher(classroom):
                        classroom.is_assigned = True
                    classroom_list.append(classroom)
                obj = {
                    "name": level.name,
                    "classroom_list": classroom_list
                }
                level_classroom_list.append(obj)
            context = {'subject': subject, 'level_classroom_list': level_classroom_list}
            return render(request, 'school/snippets/teacher_responsibility_list.html', context)
        except:
            response = {'error': "Server error occured."}
            return HttpResponse(json.dumps(response))

    def save_responsibilities(self, request, teacher):
        responsibilities = request.GET['responsibilities'].split(';')
        TeacherResponsibility.objects.filter(teacher=teacher).delete()
        for item in responsibilities:
            tk = item.split(':')
            subject = Subject.objects.get(pk=tk[0])
            classroom_fk_list = tk[1].split(',')
            TeacherResponsibility.objects.create(teacher=teacher, subject=subject, classroom_fk_list=classroom_fk_list)
        response = {'success': True}
        return HttpResponse(json.dumps(response))


@permission_required('school.ik_manage_school')
def close_session(request, *args, **kwargs):
    session = Session.get_current()
    if Score.objects.filter(session=session).count() == 0:
        # Cannot close a session without any score being set
        return HttpResponse(json.dumps({'success': True}, 'content-type: text/json'))
    session.is_active = False
    session.is_current = False
    session.save()
    event_id = request.GET['event_id']
    Event.objects.filter(pk=event_id).update(is_processed=True)
    try:
        i = session.order_number
        next_session = Session.objects.filter(school_year=get_school_year())[i + 1]
        next_session.is_active = True
        next_session.is_current = True
        next_session.save()
    except IndexError:
        pass
    return HttpResponse(json.dumps({'success': True}, 'content-type: text/json'))
