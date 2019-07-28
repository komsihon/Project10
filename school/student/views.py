import json
import logging
import os
from datetime import datetime, timedelta
from threading import Thread

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.urlresolvers import reverse
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import get_model
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render, get_object_or_404
from django.template.defaultfilters import slugify
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_protect

from echo.models import Balance
from echo.utils import notify_for_low_messaging_credit, notify_for_empty_messaging_credit, count_pages, LOW_SMS_LIMIT, \
    LOW_MAIL_LIMIT

from ikwen.accesscontrol.models import SUDO
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.billing.models import PAYMENT_CONFIRMATION, InvoiceItem, InvoiceEntry
from ikwen.billing.utils import get_next_invoice_number
from ikwen.conf.settings import WALLETS_DB_ALIAS
from ikwen.core.constants import MALE
from ikwen.core.templatetags.url_utils import strip_base_alias
from ikwen.core.models import Service
from ikwen.core.utils import get_model_admin_instance, get_mail_content, get_service_instance, add_event, send_sms, \
    increment_history_field, increment_history_field_many, XEmailMessage, add_database
from ikwen.core.views import ChangeObjectBase
from ikwen_foulassi.foulassi.admin import StudentAdmin
from ikwen_foulassi.foulassi.models import Student, Parent, Invoice, Payment, get_school_year
from ikwen_foulassi.foulassi.utils import get_payment_confirmation_email_message, get_payment_sms_text, \
    remove_student_from_parent_profile, set_student_counts
from ikwen_foulassi.reporting.models import DisciplineReport, StudentDisciplineReport
from ikwen_foulassi.reporting.utils import set_daily_counters_many
from ikwen_foulassi.school.admin import JustificatoryAdmin
from ikwen_foulassi.school.models import Classroom, Session, Score, DisciplineItem, DisciplineLogEntry, Justificatory, \
    SessionGroupScore, STUDENT_EXCLUDED

logger = logging.getLogger('ikwen')


def set_student_invoices(student):
    number = get_next_invoice_number()
    service = get_service_instance()
    school = service.config
    classroom = student.classroom
    if classroom.registration_fees:
        item = InvoiceItem(label=school.registration_fees_title, amount=classroom.registration_fees)
        entry = InvoiceEntry(item=item, short_description='------', total=classroom.registration_fees)
        if school.registration_fees_deadline:
            due_date = school.registration_fees_deadline
        else:
            due_date = datetime.now() + timedelta(days=30)
        is_tuition = True if school.is_public else False
        Invoice.objects.create(number=number, student=student, amount=classroom.registration_fees,
                               due_date=due_date, entries=[entry], is_tuition=is_tuition)
    if classroom.first_instalment:
        item = InvoiceItem(label=school.first_instalment_title, amount=classroom.first_instalment)
        entry = InvoiceEntry(item=item, short_description='------', total=classroom.first_instalment)
        if school.first_instalment_deadline:
            due_date = school.first_instalment_deadline
        else:
            due_date = datetime.now() + timedelta(days=60)
        Invoice.objects.create(number=number, student=student, amount=classroom.first_instalment_fees,
                               due_date=due_date, entries=[entry])
    if classroom.second_instalment:
        item = InvoiceItem(label=school.second_instalment_title, amount=classroom.second_instalment)
        entry = InvoiceEntry(item=item, short_description='------', total=classroom.second_instalment)
        if school.second_instalment_deadline:
            due_date = school.second_instalment_deadline
        else:
            due_date = datetime.now() + timedelta(days=90)
        Invoice.objects.create(number=number, student=student, amount=classroom.second_instalment_fees,
                               due_date=due_date, entries=[entry])
    if classroom.third_instalment:
        item = InvoiceItem(label=school.third_instalment_title, amount=classroom.third_instalment)
        entry = InvoiceEntry(item=item, short_description='------', total=classroom.third_instalment)
        if school.third_instalment_deadline:
            due_date = school.third_instalment_deadline
        else:
            due_date = datetime.now() + timedelta(days=120)
        Invoice.objects.create(number=number, student=student, amount=classroom.first_instalment_fees,
                               due_date=due_date, entries=[entry])


class ChangeStudent(ChangeObjectBase):
    template_name = 'school/student/change_student.html'
    model = Student
    model_admin = StudentAdmin

    def get_context_data(self, **kwargs):
        context = super(ChangeStudent, self).get_context_data(**kwargs)
        classroom_id = kwargs.get('classroom_id')
        if classroom_id:
            classroom = get_object_or_404(Classroom, pk=classroom_id)
            context['classroom'] = classroom
        return context

    def after_save(self, request, obj, *args, **kwargs):
        obj.tags = slugify(obj.last_name + ' ' + obj.first_name).replace('-', ' ')
        obj.save(using=UMBRELLA)
        obj.save()
        object_id = kwargs.get('object_id')
        Thread(target=set_student_counts).start()
        if object_id:
            return
        # It's a student under creation, so set a new Invoice for him
        set_student_invoices(obj)

    def get_object_list_url(self, request, obj, *args, **kwargs):
        classroom_id = kwargs.get('classroom_id')
        return reverse('school:classroom_detail', args=(classroom_id, ))


class StudentDetail(ChangeObjectBase):
    template_name = 'school/student/student_detail.html'
    model = Student
    model_admin = StudentAdmin
    context_object_name = 'student'

    def get_object(self, **kwargs):
        return get_object_or_404(Student, pk=kwargs['object_id'], is_excluded=False)

    def get_context_data(self, **kwargs):
        context = super(StudentDetail, self).get_context_data(**kwargs)
        student = context[self.context_object_name]
        classroom = student.classroom
        context['classroom'] = classroom
        context['verbose_name_plural'] = str(classroom)
        context['object_list_url'] = self.get_object_list_url(self.request, student)
        service = get_service_instance()
        student_public_url = reverse('foulassi:kid_detail', args=(service.ikwen_name, student.id, ))
        student_public_url = strip_base_alias(student_public_url)
        context['student_public_url'] = student_public_url
        return context

    def post(self, request, *args, **kwargs):
        if getattr(settings, 'IS_IKWEN', False):
            return HttpResponse(json.dumps({'error': "You're not allowed here"}))
        student_id = kwargs.get('object_id')
        if student_id:
            student = get_object_or_404(Student, pk=student_id)
        else:
            student = Student()
        object_admin = get_model_admin_instance(self.model, self.model_admin)
        model_form = object_admin.get_form(request)
        form = model_form(request.POST, instance=student)
        if form.is_valid():
            is_repeating = True if form.cleaned_data.get('is_repeating') else False
            student.registration_number = form.cleaned_data['registration_number']
            student.first_name = form.cleaned_data['first_name']
            student.last_name = form.cleaned_data['last_name']
            student.dob = form.cleaned_data['dob']
            student.is_repeating = is_repeating
            student.year_joined = form.cleaned_data['year_joined']
            student.tags = slugify(student.last_name + ' ' + student.first_name).replace('-', ' ')
            student.save()
            student.save(using=UMBRELLA)
            notice = _("Student <strong>%s</strong> successfully updated" % student.last_name)
            messages.success(request, notice)
            next_url = request.META['HTTP_REFERER']
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)

    def add_parent(self, student):
        name = self.request.GET['name'].strip()
        relation = self.request.GET['relation'].strip()
        phone = slugify(self.request.GET['phone']).replace('-', '')
        email = self.request.GET['email']
        try:
            validate_email(email)
        except ValidationError:
            response = {'error': "Invalid email"}
            return HttpResponse(json.dumps(response))
        if Parent.objects.filter(student=student, email=email).count() >= 1:
            response = {'error': _("A parent with this email already exists.")}
            return HttpResponse(json.dumps(response))
        if Parent.objects.filter(student=student, phone=phone).count() >= 1:
            response = {'error': _("A parent with this phone already exists.")}
            return HttpResponse(json.dumps(response))
        parent = Parent(student=student, name=name, relation=relation, phone=phone, email=email)
        parent.save()
        parent.save(using=UMBRELLA)
        response = {'success': True, 'id': parent.id}
        return HttpResponse(json.dumps(response))

    def render_scores(self, context):
        db = context.pop('using', 'default')
        score_list = []
        student = context[self.context_object_name]
        school_year = get_school_year(self.request)
        i = 1
        for session in Session.objects.using(db).filter(school_year=school_year):
            obj = {'session': session}
            try:
                score = Score.objects.using(db).select_related('session').get(session=session, student=student, subject__isnull=True)
                obj['value'] = score.value
                obj['rank'] = score.rank
            except Score.DoesNotExist:
                obj['value'] = '---'
                obj['rank'] = '---'
            score_list.append(obj)
            if i % 2 == 0:
                try:
                    session_group = session.session_group
                    score = SessionGroupScore.objects.using(db)\
                        .select_related('session_group').get(session_group=session_group, student=student,
                                                             subject__isnull=True)
                    obj = {'session': '', 'value': score.value, 'rank': score.rank}
                except SessionGroupScore.DoesNotExist:
                    obj = {'session': '', 'value': '---', 'rank': '---'}
                score_list.append(obj)
            i += 1
        if i % 2 == 0:
            try:
                session_group = session.session_group
                score = SessionGroupScore.objects.using(db).get(session_group=session_group, student=student,
                                                                subject__isnull=True)
                obj = {'session': '', 'value': score.value, 'rank': score.rank}
            except SessionGroupScore.DoesNotExist:
                obj = {'session': '', 'value': '---', 'rank': '---'}
            score_list.append(obj)
        context['score_list'] = score_list
        return render(self.request, 'school/snippets/student/scores.html', context)

    def render_discipline(self, context):
        db = context.pop('using', 'default')
        student = context[self.context_object_name]
        summary = []
        queryset = DisciplineLogEntry.objects.using(db)
        for item in DisciplineItem.objects.using(db).all():
            item.count = 0
            for obj in queryset.filter(item=item, student=student):
                item.count += obj.count
            summary.append(item)
        discipline_log = DisciplineLogEntry.objects.using(db).select_related('item, student').filter(student=student).order_by('-id')
        context['summary'] = summary
        context['discipline_log'] = discipline_log
        context['discipline_item_list'] = DisciplineItem.objects.using(db).filter(editable=True)\
            .exclude(slug__in=[DisciplineItem.PARENT_CONVOCATION, DisciplineItem.EXCLUSION])
        context['parent_convocation'] = DisciplineItem.objects.using(db).get(slug=DisciplineItem.PARENT_CONVOCATION)
        context['exclusion'] = DisciplineItem.objects.using(db).get(slug=DisciplineItem.EXCLUSION)
        return render(self.request, 'school/snippets/student/discipline.html', context)

    def render_billing(self, context):
        db = context.pop('using', 'default')
        student = context[self.context_object_name]
        invoice_list = list(Invoice.objects.using(db).filter(student=student))
        pending_invoice_list = Invoice.objects.using(db).filter(student=student, status=Invoice.PENDING)
        payment_list = Payment.objects.using(db).select_related('invoice').filter(invoice__in=invoice_list)
        context['pending_invoice_list'] = pending_invoice_list
        context['payment_list'] = payment_list
        return render(self.request, 'school/snippets/student/billing.html', context)

    def cash_in(self, context):
        if getattr(settings, 'IS_IKWEN', False):
            return HttpResponse(json.dumps({'error': "You're not allowed here"}))
        student = context[self.context_object_name]
        student.is_confirmed = True
        student.save()
        invoice_id = self.request.GET['invoice_id']
        amount = self.request.GET['amount']
        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError()
        except ValueError:
            return HttpResponse(json.dumps({'error': _("Invalid amount")}))
        sms_notification = self.request.GET.get('sms_notification', False)
        invoice = Invoice.objects.get(pk=invoice_id)
        payment = Payment.objects.create(invoice=invoice, amount=amount, method=Payment.CASH, cashier=self.request.user)
        invoice.paid = amount
        invoice.save()
        response = {'success': True}
        service = get_service_instance()
        if getattr(settings, 'DEBUG', False):
            sudo_group = Group.objects.get(name=SUDO)
            add_event(service, PAYMENT_CONFIRMATION, group_id=sudo_group.id, object_id=invoice.id)
        else:
            try:
                sudo_group = Group.objects.get(name=SUDO)
                add_event(service, PAYMENT_CONFIRMATION, group_id=sudo_group.id, object_id=invoice.id)
            except Group.DoesNotExist:
                pass
        parents = student.parent_set.all()
        if parents.count() <= 0:
            return HttpResponse(json.dumps(response))
        config = service.config
        for parent in parents:
            member = parent.member
            if member:
                add_event(service, PAYMENT_CONFIRMATION, member=member, object_id=invoice.id)
            if sms_notification:
                sms_text = get_payment_sms_text(payment, str(student))
                send_sms(parent.get_phone(), sms_text)
        recipients = [parent.get_email() for parent in parents if parent.get_email()]
        service = get_service_instance()
        if len(recipients) > 0:
            balance = Balance.objects.using(WALLETS_DB_ALIAS).get(service_id=service.id)
            if 0 < balance.mail_count < LOW_MAIL_LIMIT:
                notify_for_low_messaging_credit(service, balance)
            if balance.mail_count <= 0 and not getattr(settings, 'UNIT_TESTING', False):
                notify_for_empty_messaging_credit(service, balance)
            if balance.mail_count < len(recipients):
                return HttpResponse(json.dumps(response))
            subject, message = get_payment_confirmation_email_message(payment, parents[0].get_name(), str(student))
            html_content = get_mail_content(subject, message, template_name='billing/mails/notice.html')
            sender = '%s <no-reply@%s>' % (config.company_name, service.domain)
            msg = XEmailMessage(subject, html_content, sender, recipients)
            msg.content_subtype = "html"
            try:
                with transaction.atomic(using='wallets'):
                    balance.mail_count -= len(recipients)
                    balance.save()
                    Thread(target=lambda m: m.send(), args=(msg,)).start()
            except:
                pass
        return HttpResponse(json.dumps({'success': True}))

    def add_discipline_log_entry(self, context, action):
        if getattr(settings, 'IS_IKWEN', False):
            return HttpResponse(json.dumps({'error': "You're not allowed here"}))
        service = get_service_instance()
        config = service.config
        student = context['student']
        if action == DisciplineItem.PARENT_CONVOCATION:
            item = DisciplineItem.objects.get(slug=DisciplineItem.PARENT_CONVOCATION)
            count = 1
            happened_on = self.request.GET['happened_on']
            tk = happened_on.split('-')
            happened_on = datetime(int(tk[0]), int(tk[1]), int(tk[2]))
            text = _("You are summoned to school on %(summon_date)s about your "
                     "child %(student)s" % {'summon_date': happened_on.strftime("%d/%b/%y"), 'student': student})
        elif action == DisciplineItem.EXCLUSION:
            item = DisciplineItem.objects.get(slug=DisciplineItem.EXCLUSION)
            count = 1
            happened_on = datetime.now()
            text = _("We regret to inform you that your child %s has been excluded from our school." % student)
            student.is_excluded = True
            student.save()
            student.save(using=UMBRELLA)
            service = get_service_instance()
            for parent in student.parent_set.using(UMBRELLA).all():
                member = parent.member
                if member:
                    add_event(service, STUDENT_EXCLUDED, member=member, object_id=student.id)
            Thread(target=set_student_counts).start()
        else:
            item = DisciplineItem.objects.get(pk=self.request.GET['item_id'])
            count = float(self.request.GET['count'])
            happened_on = self.request.GET['happened_on']
            tk = happened_on.split('-')
            happened_on = datetime(int(tk[0]), int(tk[1]), int(tk[2]))
            if item.slug == DisciplineItem.LATENESS:
                text = _("Your child %(student)s has been %(count)s "
                         "hour(s) late." % {'student': student, 'count': count})
            elif item.slug == DisciplineItem.ABSENCE:
                text = _("Your child %(student)s has been absent for "
                         "%(count)s hour(s)." % {'student': student, 'count': count})
            else:
                text = _("New information about discipline of your child %s have been published." % student)

        if happened_on < config.back_to_school_date:
            response = {'error': _("Cannot set an event earlier than Back to school date.")}
            return HttpResponse(json.dumps(response))

        details = self.request.GET['details']
        entry = DisciplineLogEntry.objects.create(item=item, student=student,
                                                  details=details, count=count, happened_on=happened_on)
        classroom = student.classroom
        level = classroom.level
        discipline_report, update = DisciplineReport.objects.get_or_create(discipline_item=item, level=None, classroom=None)
        level_discipline_report, update = DisciplineReport.objects.get_or_create(discipline_item=item, level=level)
        classroom_discipline_report, update = DisciplineReport.objects.get_or_create(discipline_item=item, classroom=classroom)
        student_discipline_report, update = StudentDisciplineReport.objects.get_or_create(discipline_item=item, student=student)
        set_daily_counters_many(discipline_report, level_discipline_report,
                                classroom_discipline_report, student_discipline_report)
        diff = datetime.now() - happened_on
        if diff.days > 0:
            rev_index = diff.days + 1
        else:  # Means that happened_on was set to a future date
            rev_index = 1
        if student.gender == MALE:
            increment_history_field_many('boys_history', count, -rev_index,
                                         discipline_report, level_discipline_report, classroom_discipline_report)
        else:
            increment_history_field_many('girls_history', count, -rev_index,
                                         discipline_report, level_discipline_report, classroom_discipline_report)
        increment_history_field_many('total_history', count, -rev_index,
                                     discipline_report, level_discipline_report, classroom_discipline_report)
        student_discipline_report.last_add_on = datetime.now()
        increment_history_field(student_discipline_report, 'count_history', count, -rev_index)

        response = {'success': True, 'entry': entry.to_dict()}
        if self.request.GET['send_sms']:
            recipients = [parent.phone for parent in student.parent_set.all()]
            page_count = count_pages(text)
            balance = Balance.objects.using(WALLETS_DB_ALIAS).get(service_id=service.id)
            if 0 < balance.sms_count < LOW_SMS_LIMIT:
                notify_for_low_messaging_credit(service, balance)
            if balance.sms_count <= 0:
                notify_for_empty_messaging_credit(service, balance)
                return HttpResponse(json.dumps(response))
            if balance.sms_count < len(recipients):
                return HttpResponse(json.dumps(response))
            for phone in recipients:
                phone = slugify(phone).replace('-', '')
                if len(phone) == 9:
                    phone = '237' + phone
                try:
                    with transaction.atomic(using='wallets'):
                        balance.sms_count -= page_count
                        balance.save()
                        Thread(target=send_sms, args=(phone, text, 'ikwen')).start()
                except:
                    pass

        return HttpResponse(json.dumps(response))

    def add_invoice(self, context):
        if getattr(settings, 'IS_IKWEN', False):
            return HttpResponse(json.dumps({'error': "You're not allowed here"}))
        student = context['student']
        label = self.request.GET['label']
        amount = float(self.request.GET['amount'])
        due_date = self.request.GET['due_date']
        item = InvoiceItem(label=label, amount=amount)
        entries = [InvoiceEntry(item=item, total=amount)]
        number = get_next_invoice_number()
        invoice = Invoice.objects.create(number=number, student=student,
                                         entries=entries, amount=amount, due_date=due_date)
        response = {'success': True, 'id': invoice.id}
        return HttpResponse(json.dumps(response))

    def delete_object(self, student=None):
        selection = self.request.GET['selection'].split(',')
        model_name = self.request.GET.get('model_name')
        if model_name:
            if getattr(settings, 'IS_IKWEN', False) and model_name != 'foulassi.Parent':
                return HttpResponse(json.dumps({'error': "You're not allowed here"}))
            model = get_model(*model_name.split('.'))
        else:
            model = self.model
        deleted = []
        for pk in selection:
            obj = model._default_manager.get(pk=pk)
            obj.delete()
            if model_name == 'foulassi.Parent':
                if getattr(settings, 'DEBUG', False):
                    remove_student_from_parent_profile(student, obj.email, obj.phone)
                else:
                    Thread(target=remove_student_from_parent_profile, args=(student, obj.email, obj.phone)).start()
            deleted.append(pk)

        else:
            message = "%d item(s) deleted." % len(selection)
        response = {
            'message': message,
            'deleted': deleted
        }
        return HttpResponse(json.dumps(response), content_type='application/json')

    def render_to_response(self, context, **response_kwargs):
        action = self.request.GET.get('action')
        tab = self.request.GET.get('tab')
        if tab == 'scores':
            return self.render_scores(context)
        elif tab == 'discipline':
            return self.render_discipline(context)
        elif tab == 'billing':
            return self.render_billing(context)
        elif action == 'add_parent':
            return self.add_parent(context['student'])
        elif action == 'add_invoice':
            return self.add_invoice(context)
        elif action == 'cash_in':
            return self.cash_in(context)
        elif action == 'add_discipline_log_entry' or action == DisciplineItem.PARENT_CONVOCATION:
            return self.add_discipline_log_entry(context, action)
        elif action == 'exclude':
            return self.exclude(context['student'])
        elif action == 'delete':
            return self.delete_object(context['student'])
        elif action == 'remind':
            pass
        return super(StudentDetail, self).render_to_response(context, **response_kwargs)

    def get_object_list_url(self, request, obj, *args, **kwargs):
        return reverse('school:classroom_detail', args=(obj.classroom.id, ))


class ChangeJustificatory(ChangeObjectBase):
    template_name = 'school/change_justificatory.html'
    model = Justificatory
    model_admin = JustificatoryAdmin

    def get_object(self, **kwargs):
        if getattr(settings, 'IS_UMBRELLA', False):
            ikwen_name = kwargs['ikwen_name']
            object_id = kwargs['object_id']
            try:
                school = Service.objects.get(project_name_slug=ikwen_name)
                add_database(school.database)
                obj = Justificatory.objects.using(school.database).select_related('entry').get(pk=object_id)
                # if not student.kid_fees_paid:
                #     return HttpResponseRedirect(reverse('foulassi:kid_list', args=(ikwen_name, )))
            except Justificatory.DoesNotExist:
                raise Http404("School or student not found")
            return obj
        return super(ChangeJustificatory, self).get_object(**kwargs)

    def get_object_list_url(self, request, obj, *args, **kwargs):
        if obj:
            entry = obj.entry
        else:
            entry_id = self.request.GET.get('entry_id')
            entry = get_object_or_404(DisciplineLogEntry, pk=entry_id)
        return reverse('school:student_detail', args=(entry.student.id, )) + '?showTab=discipline'

    def get_context_data(self, **kwargs):
        context = super(ChangeJustificatory, self).get_context_data(**kwargs)
        entry_id = self.request.GET.get('entry_id')
        if entry_id:
            entry = get_object_or_404(DisciplineLogEntry, pk=entry_id)
        else:
            justificatory = context[self.context_object_name]
            entry = justificatory.entry
        student = entry.student
        context['verbose_name_plural'] = str(student.classroom)
        context['student'] = student
        context['classroom_url'] = reverse('school:classroom_detail', args=(student.classroom.id, ))
        context['entry'] = entry
        return context

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
            entry_id = self.request.GET['entry_id']
            entry = get_object_or_404(DisciplineLogEntry, pk=entry_id)
            try:
                entry.justificatory.delete()  # Delete any previous justificatory as there is only one per entry
            except:
                pass
            obj.details = form.cleaned_data['details']
            obj.entry = entry
            obj.save()
            entry.is_justified = True
            entry.save()
            image_url = request.POST.get('image_url')
            if image_url:
                s = get_service_instance()
                image_field_name = request.POST.get('image_field_name', 'image')
                image_field = obj.__getattribute__(image_field_name)
                if not image_field.name or image_url != image_field.url:
                    filename = image_url.split('/')[-1]
                    media_root = getattr(settings, 'MEDIA_ROOT')
                    media_url = getattr(settings, 'MEDIA_URL')
                    image_url = image_url.replace(media_url, '')
                    try:
                        with open(media_root + image_url, 'r') as f:
                            content = File(f)
                            destination = media_root + obj.UPLOAD_TO + "/" + s.project_name_slug + '_' + filename
                            image_field.save(destination, content)
                        os.unlink(media_root + image_url)
                    except IOError as e:
                        if getattr(settings, 'DEBUG', False):
                            raise e
                        return {'error': 'File failed to upload. May be invalid or corrupted image file'}

            next_url = self.get_object_list_url(request, obj, *args, **kwargs)
            if object_id:
                messages.success(request, obj._meta.verbose_name.capitalize() + ' <strong>' + str(obj).decode('utf8') + '</strong> ' + _('successfully updated'))
            else:
                messages.success(request, obj._meta.verbose_name.capitalize() + ' <strong>' + str(obj).decode('utf8') + '</strong> ' + _('successfully created'))
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, self.template_name, context)
