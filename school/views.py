import json
import os
from threading import Thread
from time import strptime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import Group
from django.core.files import File
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.utils.translation import gettext as _
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import TemplateView
from ikwen.accesscontrol.models import Member, SUDO
from ikwen.billing.models import Invoice, Payment, PAYMENT_CONFIRMATION
from ikwen.billing.utils import get_payment_confirmation_message, share_payment_and_set_stats
from ikwen.core.constants import MALE
from ikwen.core.models import Config
from ikwen.core.utils import get_model_admin_instance, get_mail_content, get_service_instance, add_event, send_sms
from ikwen.core.views import HybridListView, ChangeObjectBase
from ikwen_foulassi.foulassi.admin import StudentAdmin
from ikwen_foulassi.foulassi.models import Student, Parent, Teacher
from ikwen_foulassi.foulassi.utils import set_counters
from ikwen_foulassi.school.admin import LevelAdmin, SubjectAdmin, SessionAdmin, ClassroomAdmin
from ikwen_foulassi.school.models import Level, Classroom, Session, get_subject_list, Subject, Score, ScoreBase, \
    ScoreUpdateRequest, SubjectSession


class LevelList(HybridListView):
    model = Level
    context_object_name = 'level_list'
    template_name = 'school/level_list.html'


class ChangeLevel(ChangeObjectBase):
    template_name = 'school/change_level.html'
    model = Level
    model_admin = LevelAdmin

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        level_id = kwargs.get('object_id')
        subjects = request.POST.get('subjects')
        if level_id:
            obj = get_object_or_404(self.model, pk=level_id)
        else:
            obj = Level()
        object_admin = get_model_admin_instance(self.model, self.model_admin)
        ModelForm = object_admin.get_form(request)
        form = ModelForm(request.POST, instance=obj)
        if form.is_valid():
            obj.name = form.cleaned_data['name']
            obj.tuition_fees = form.cleaned_data['tuition_fees']
            if subjects:
                subject_list = subjects.split(';')
                obj.subject_fk_list = subject_list
            obj.save()
            url_name = 'school:level_list'
            next_url = reverse(url_name)
            notice = _(obj._meta.verbose_name) + ' ' + _('successfully updated')
            messages.success(request, notice)
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)


class SubjectList(HybridListView):
    model = Subject
    context_object_name = 'subject_list'
    template_name = 'school/subject_list.html'


class ChangeSubject(ChangeObjectBase):
    template_name = 'school/change_subject.html'
    model = Subject
    model_admin = SubjectAdmin


class SessionList(HybridListView):
    model = Session
    context_object_name = 'session_list'
    template_name = 'school/session_list.html'


class ChangeSession(ChangeObjectBase):
    template_name = 'school/change_session.html'
    model = Session
    model_admin = SessionAdmin


class ClassroomList(HybridListView):
    model = Level
    context_object_name = 'classroom_list'
    template_name = 'school/classroom_list.html'

    def get_context_data(self, **kwargs):
        context = super(ClassroomList, self).get_context_data(**kwargs)
        classroom_list = []
        for level in Level.objects.all().order_by('order_of_appearance', 'name'):
            obj = {
                "name": level.name,
                "classrooms": Classroom.objects.filter(level=level)
            }
            classroom_list.append(obj)
        context['classroom_list'] = classroom_list
        return context


class AddClassroom(ChangeObjectBase):
    template_name = 'school/add_classroom.html'
    model = Classroom
    model_admin = ClassroomAdmin

    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        obj = Classroom()
        object_admin = get_model_admin_instance(self.model, self.model_admin)
        ModelForm = object_admin.get_form(request)
        form = ModelForm(request.POST)
        if form.is_valid():
            obj.level = form.cleaned_data['level']
            obj.name = form.cleaned_data['name']
            obj.tuition_fees = form.cleaned_data['tuition_fees']
            subjects = request.POST['subjects'].split(';')
            obj.subject_fk_list = subjects
            obj.save()
            url_name = 'school:classroom_list'
            next_url = reverse(url_name)
            notice = _(obj._meta.verbose_name) + ' ' + _('successfully updated')
            messages.success(request, notice)
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)


class ClassroomDetail(TemplateView):
    template_name = 'school/classroom_detail.html'

    def get_context_data(self, **kwargs):
        context = super(ClassroomDetail, self).get_context_data(**kwargs)
        classroom_id = kwargs.get('object_id')
        if classroom_id:
            classroom = get_object_or_404(Classroom, pk=classroom_id)
            context['classroom'] = classroom
            context['subject_list'] = get_subject_list(classroom)
        context['sessions'] = Session.objects.all()
        return context

    def mark(self, request, classroom):
        subject_id = request.POST['subject_id']
        session_id = request.POST['session_id']
        subject = Subject.objects.get(pk=subject_id)
        session = Session.objects.get(pk=session_id)
        level = classroom.level
        scores = request.POST['scores']
        score_list = json.loads(scores)
        update_list = []
        classroom_stats, change = SubjectSession.objects.get_or_create(subject=subject, session=session, classroom=classroom)
        level_stats, change = SubjectSession.objects.get_or_create(subject=subject, session=session, level=level)
        boys_participation, boys_highest_score, boys_lowest_score, boys_total_scores, boys_success = 0, 0, 20, 0, 0
        girls_participation, girls_highest_score, girls_lowest_score, girls_total_scores, girls_success = 0, 0, 20, 0, 0
        i = session.order_number
        set_counters(classroom_stats, i)
        set_counters(level_stats, i)
        level_stats.boys_lowest_score_history[i] = 20
        level_stats.girls_lowest_score_history[i] = 20
        for item in score_list:
            student_id = item['student_id']
            value = item['score']
            try:
                student = Student.objects.get(pk=student_id)
                if student.gender == MALE:
                    boys_participation += 1
                    boys_highest_score = max(boys_highest_score, value)
                    boys_lowest_score = min(boys_lowest_score, value)
                    boys_total_scores += value
                    if value >= 10:
                        boys_success += 1
                else:
                    girls_participation += 1
                    girls_highest_score = max(girls_highest_score, value)
                    girls_lowest_score = min(girls_lowest_score, value)
                    girls_total_scores += value
                    if value >= 10:
                        girls_success += 1
                try:
                    Score.objects.get(session=session, subject=subject, student=student)
                    score_update = ScoreBase(student=student, value=value)
                    update_list.append(score_update)
                except Score.DoesNotExist:
                    Score.objects.create(session=session, subject=subject, student=student, value=value)
            except Student.DoesNotExist:
                pass

        classroom_stats.boys_participation_history[i] = boys_participation
        classroom_stats.boys_highest_score_history[i] = boys_highest_score
        classroom_stats.boys_lowest_score_history[i] = boys_lowest_score
        classroom_boys_avg = float(boys_total_scores) / boys_participation if boys_participation > 0 else 0
        classroom_stats.boys_avg_score_history[i] = round(classroom_boys_avg, 2)
        classroom_stats.boys_success_history[i] = boys_success

        if level_stats.boys_avg_score_history[i] == 0:
            level_boys_total_score = boys_total_scores
            level_boys_total_participation = boys_participation
        else:
            level_boys_total_score = level_stats.boys_avg_score_history[i] * level_stats.boys_participation_history[i]
            level_boys_total_score += boys_total_scores
            level_boys_total_participation = level_stats.boys_participation_history[i] + boys_participation
        level_boys_avg = float(level_boys_total_score) / level_boys_total_participation if level_boys_total_participation > 0 else 0
        level_stats.boys_avg_score_history[i] = round(level_boys_avg, 2)
        level_stats.boys_participation_history[i] += boys_participation
        level_stats.boys_highest_score_history[i] = max(level_stats.boys_highest_score_history[i], boys_highest_score)
        level_stats.boys_lowest_score_history[i] = min(level_stats.boys_lowest_score_history[i], boys_lowest_score)
        level_stats.boys_success_history[i] += boys_success

        classroom_stats.girls_participation_history[i] = girls_participation
        classroom_stats.girls_highest_score_history[i] = girls_highest_score
        classroom_stats.girls_lowest_score_history[i] = girls_lowest_score
        classroom_girls_avg = float(girls_total_scores) / girls_participation if girls_participation > 0 else 0
        classroom_stats.girls_avg_score_history[i] = round(classroom_girls_avg, 2)
        classroom_stats.girls_success_history[i] = girls_success
        classroom_stats.save()

        if level_stats.girls_avg_score_history[i] == 0:
            level_girls_total_score = girls_total_scores
            level_girls_total_participation = girls_participation
        else:
            level_girls_total_score = level_stats.girls_avg_score_history[i] * level_stats.girls_participation_history[i]
            level_girls_total_score += girls_total_scores
            level_girls_total_participation = level_stats.girls_participation_history[i] + girls_participation
        level_girls_avg = float(level_girls_total_score) / level_girls_total_participation if level_girls_total_participation > 0 else 0
        level_stats.girls_avg_score_history[i] = round(level_girls_avg, 2)
        level_stats.girls_participation_history[i] += girls_participation
        level_stats.girls_highest_score_history[i] = max(level_stats.girls_highest_score_history[i], girls_highest_score)
        level_stats.girls_lowest_score_history[i] = min(level_stats.girls_lowest_score_history[i], girls_lowest_score)
        level_stats.girls_success_history[i] += girls_success
        level_stats.save()

        if update_list:
            ScoreUpdateRequest.objects.create(session=session, subject=subject,
                                              member=self.request.user, update_list=update_list)
        response = {'success': True}
        return HttpResponse(json.dumps(response))

    def render_to_response(self, context, **response_kwargs):
        action = self.request.GET.get('action')
        classroom = context['classroom']
        if action == 'change':
            subjects = self.request.GET.get('subjects')
            professor_id = self.request.GET.get('professor_id')
            leader_id = self.request.GET.get('leader_id')
            name = self.request.GET.get('name')
            if subjects:
                subject_list = subjects.split(';')
                classroom.subject_fk_list = subject_list
            if professor_id:
                professor = get_object_or_404(Teacher, pk=professor_id)
                classroom.professor = professor
            if leader_id:
                Student.objects.filter(classroom=classroom).update(is_leader=False)
                student = get_object_or_404(Student, pk=leader_id)
                student.is_leader = True
                student.save()
            classroom.name = name
            classroom.save()
            response = {'success': True}
            return HttpResponse(json.dumps(response))
        return super(ClassroomDetail, self).render_to_response(context, **response_kwargs)

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        if action == 'mark':
            classroom = Classroom.objects.get(pk=kwargs['object_id'])
            return self.mark(request, classroom)


class ChangeStudent(ChangeObjectBase):
    template_name = 'school/student_detail.html'
    model = Student
    model_admin = StudentAdmin

    def get_context_data(self, **kwargs):
        context = super(ChangeStudent, self).get_context_data(**kwargs)
        student_id = kwargs.get('object_id')
        if student_id:
            student = get_object_or_404(Classroom, pk=student_id)
            context['student'] = student
        return context

    def post(self, request, *args, **kwargs):
        student_id = kwargs.get('object_id')
        if student_id:
            student = get_object_or_404(Student, pk=student_id)
        else:
            student = Student()
        object_admin = get_model_admin_instance(self.model, self.model_admin)
        model_form = object_admin.get_form(request)
        form = model_form(request.POST, instance=student)
        if form.is_valid():
            image_url = request.POST.get('image_url')
            parents = request.POST.get('parents')
            is_repeating = True if form.cleaned_data.get('is_repeating') else False
            student.first_name = form.cleaned_data['first_name']
            student.last_name = form.cleaned_data['last_name']
            student.dob = form.cleaned_data['dob']
            student.is_repeating = is_repeating
            student.year_joined = form.cleaned_data['year_joined']
            parent_fk_list = []
            if parents:
                parents = json.loads(parents)
                for obj in parents:
                    obj_id, member_id, name, phone, email, relation = obj['id'], obj['member_id'], obj['name'], obj['phone'], obj['email'], obj['relation']
                    if obj_id:
                        try:
                            parent = Parent.objects.get(pk=obj_id)
                        except Parent.DoesNotExist:
                            continue
                    else:
                        parent = Parent()
                    parent.relation = relation
                    if member_id:
                        parent.member = Member.objects.get(pk=member_id)
                    else:
                        parent.name = name
                        parent.phone = phone
                        parent.email = email
                    parent.save()
                    parent_fk_list.append(parent.id)
                student.parent_fk_list = parent_fk_list
            if image_url:
                if not student.photo.name or image_url != student.photo.url:
                    filename = image_url.split('/')[-1]
                    media_root = getattr(settings, 'MEDIA_ROOT')
                    media_url = getattr(settings, 'MEDIA_URL')
                    image_url = image_url.replace(media_url, '')
                    try:
                        with open(media_root + image_url, 'r') as f:
                            content = File(f)
                            destination = media_root + Student.PHOTOS_FOLDER + "/" + filename
                            student.photo.save(destination, content)
                        os.unlink(media_root + image_url)
                    except IOError as e:
                        if getattr(settings, 'DEBUG', False):
                            raise e
                        return {'error': 'File failed to upload. May be invalid or corrupted image file'}
            student.save()
            if student_id:
                notice = _(student._meta.verbose_name) + ' ' + _('successfully updated')
            else:
                notice = _(student._meta.verbose_name) + ' ' + _('successfully added')
            messages.success(request, notice)
            return HttpResponseRedirect(reverse('school:change_student'))
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)

    def render_info(self, context):
        return render(self.request, 'school/snippets/student/information.html', context)

    def render_scores(self, context):
        return render(self.request, 'school/snippets/student/scores.html', context)

    def render_accounting(self, context):
        return render(self.request, 'school/snippets/student/accounting.html', context)

    def render_to_response(self, context, **response_kwargs):
        action = self.request.GET.get('action')
        tab = self.request.GET.get('tab')
        if tab == 'info':
            return self.render_info(context)
        elif tab == 'scores':
            return self.render_scores(context)
        elif tab == 'accounting':
            return self.render_accounting(context)
        elif action == 'cash_in':
            invoice_id = self.request.GET['invoice_id']
            amount = self.request.GET['amount']
            invoice = Invoice.objects.get(pk=invoice_id)
            payment = Payment.objects.create(invoice=invoice, amount=amount,
                                             method=Payment.CASH, cashier=self.request.user)
            member = invoice.subscription.member
            service = get_service_instance()
            config = service.config
            share_payment_and_set_stats(invoice, invoice.months_count)

            if getattr(settings, 'DEBUG', False):
                sudo_group = Group.objects.get(name=SUDO)
                add_event(service, PAYMENT_CONFIRMATION, group_id=sudo_group.id, object_id=invoice.id)
            else:
                try:
                    sudo_group = Group.objects.get(name=SUDO)
                    add_event(service, PAYMENT_CONFIRMATION, group_id=sudo_group.id, object_id=invoice.id)
                except Group.DoesNotExist:
                    pass

            if member:
                add_event(service, PAYMENT_CONFIRMATION, member=member, object_id=invoice.id)
                subject, message, sms_text = get_payment_confirmation_message(payment, member)
                if member.email:
                    html_content = get_mail_content(subject, message, template_name='billing/mails/notice.html')
                    sender = '%s <no-reply@%s>' % (config.company_name, service.domain)
                    msg = EmailMessage(subject, html_content, sender, [member.email])
                    msg.content_subtype = "html"
                    Thread(target=lambda m: m.send(), args=(msg,)).start()
                if sms_text:
                    if member.phone:
                        if config.sms_sending_method == Config.HTTP_API:
                            send_sms(member.phone, sms_text)
        elif action == 'new_invoice':
            pass
        elif action == 'remind':
            pass
        return super(ChangeStudent, self).render_to_response(context, **response_kwargs)
