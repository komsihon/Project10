import json
from collections import OrderedDict
from datetime import timedelta, datetime

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.db.models import Sum, Q
from django.http.response import HttpResponseRedirect, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import urlquote
from django.views.generic import TemplateView

from ikwen.conf.settings import WALLETS_DB_ALIAS
from ikwen.core.models import Service
from ikwen.core.utils import add_database, get_service_instance
from ikwen.billing.models import MoMoTransaction
from ikwen.billing.mtnmomo.views import MTN_MOMO
from ikwen_foulassi.foulassi.utils import can_access_kid_detail

from ikwen_foulassi.foulassi.models import ParentProfile, Student, Invoice, Payment, Event, Parent
from ikwen_foulassi.school.models import get_subject_list, Justificatory

from ikwen_foulassi.school.student.views import StudentDetail, ChangeJustificatory


class EventList(TemplateView):
    template_name = 'foulassi/event_list.html'
    MIN_DISPLAY = 10

    def get_context_data(self, **kwargs):
        context = super(EventList, self).get_context_data(**kwargs)
        event_list = list(Event.objects.filter(is_processed=False).order_by('-id'))
        count_pending = len(event_list)
        if count_pending < self.MIN_DISPLAY:
            extra = self.MIN_DISPLAY - count_pending
            event_list.extend(list(Event.objects.filter(is_processed=True).order_by('-id')[:extra]))
        date_list = list(set([ev.created_on.date() for ev in event_list]))
        date_list.sort(reverse=True)
        event_collection = OrderedDict()
        for date in date_list:
            event_collection[date] = [ev.render(self.request) for ev in event_list if ev.created_on.date() == date]
        context['event_collection'] = event_collection
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'mark_as_processed':
            return self.mark_as_processed(request)
        return super(EventList, self).get(request, *args, **kwargs)

    def mark_as_processed(self, request):
        event_id = request.GET['event_id']
        Event.objects.filter(pk=event_id).update(is_processed=True)
        return HttpResponse(json.dumps({'success': True}, 'content-type: text/json'))


class KidList(TemplateView):
    template_name = 'foulassi/kid_list.html'

    def get_context_data(self, **kwargs):
        context = super(KidList, self).get_context_data(**kwargs)
        user = self.request.user
        parent_profile, update = ParentProfile.objects.get_or_create(member=user)
        kid_list = parent_profile.student_list
        kid_fk_list = [kid.pk for kid in kid_list]
        suggestion_key = user.username + 'suggestion_list'
        suggestion_list = cache.get(suggestion_key)
        # suggestion_list = None
        if suggestion_list is None:
            suggestion_list = []
            for obj in Parent.objects.select_related('student').filter(Q(email=user.email) | Q(phone=user.phone)):
                if obj.student.id in kid_fk_list:
                    continue
                try:
                    suggestion_list.append(obj.student)
                    kid_fk_list.append(obj.student.id)
                except:
                    pass
            cache.set(suggestion_key, suggestion_list, 5 * 60)
        context['suggestion_list'] = suggestion_list
        context['kid_list'] = kid_list
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'accept_suggestion':
            return self.accept_suggestion(request)
        elif action == 'refuse_suggestion':
            return self.refuse_suggestion(request)
        return super(KidList, self).get(request, *args, **kwargs)

    def accept_suggestion(self, request):
        user = request.user
        student_id = request.GET['student_id']
        student = Student.objects.get(pk=student_id)
        parent_profile, update = ParentProfile.objects.get_or_create(member=user)
        if student not in parent_profile.student_list:
            parent_profile.student_list.insert(0, student)
            parent_profile.save()
            suggestion_key = user.username + 'suggestion_list'
            cache.delete(suggestion_key)
        return HttpResponse(json.dumps({'success': True}, 'content-type: text/json'))

    def refuse_suggestion(self, request):
        user = request.user
        student_id = request.GET['student_id']
        student = Student.objects.get(pk=student_id)
        db = student.school.database
        add_database(db)
        Parent.objects.using(db).filter(Q(email=user.email) | Q(phone=user.phone), student=student).delete()
        suggestion_key = user.username + 'suggestion_list'
        cache.delete(suggestion_key)
        return HttpResponse(json.dumps({'success': True}, 'content-type: text/json'))


class KidDetail(StudentDetail):
    template_name = 'foulassi/kid_detail.html'

    def get_object(self, **kwargs):
        ikwen_name = kwargs['ikwen_name']
        student_id = kwargs['student_id']
        try:
            school = Service.objects.get(project_name_slug=ikwen_name)
            add_database(school.database)
            student = Student.objects.using(school.database).select_related('school, classroom').get(pk=student_id)
            # if not student.kid_fees_paid:
            #     return HttpResponseRedirect(reverse('foulassi:kid_list', args=(ikwen_name, )))
        except ObjectDoesNotExist:
            raise Http404("School or student not found")
        return student

    def get_context_data(self, **kwargs):
        context = super(KidDetail, self).get_context_data(**kwargs)
        user = self.request.user
        parent_profile = get_object_or_404(ParentProfile, member=user)
        student = context['student']
        db = student.school.database
        add_database(db)
        subject_list = get_subject_list(student.classroom, using=db)
        for subject in subject_list:
            subject.score_list = student.get_score_list(subject, using=db)
        context['subject_list'] = subject_list
        kid_list = parent_profile.student_list
        # kid_list.remove(student)
        context['kid_list'] = kid_list
        context['using'] = db
        parent1 = Parent.objects.filter(student=student)[0]
        context['is_first_parent'] = parent1.email == user.email or parent1.phone == user.phone
        return context

    def get(self, request, *args, **kwargs):
        user = request.user
        can_access = can_access_kid_detail(request, **kwargs)
        if not can_access:
            if user.is_authenticated():
                next_url = reverse('foulassi:access_denied')
            else:
                next_url = reverse('ikwen:sign_in') + '?next=' + request.get_full_path()
            return HttpResponseRedirect(next_url)
        return super(KidDetail, self).get(request, *args, **kwargs)


class ShowJustificatory(ChangeJustificatory):
    template_name = 'foulassi/show_justificatory.html'

    def get_object(self, **kwargs):
        ikwen_name = kwargs['ikwen_name']
        object_id = kwargs['object_id']
        try:
            school = Service.objects.get(project_name_slug=ikwen_name)
            add_database(school.database)
            obj = Justificatory.objects.using(school.database).select_related('entry').get(pk=object_id)
            # if not student.kid_fees_paid:
            #     return HttpResponseRedirect(reverse('foulassi:kid_list', args=(ikwen_name, )))
        except Justificatory.DoesNotExist:
            raise Http404("No justficicatory found with this ID.")
        return obj

    def get_context_data(self, **kwargs):
        context = super(ShowJustificatory, self).get_context_data(**kwargs)
        user = self.request.user
        parent_profile = get_object_or_404(ParentProfile, member=user)
        context['kid_list'] = parent_profile.student_list
        return context


class AccessDenied(TemplateView):
    template_name = 'foulassi/access_denied.html'


def set_invoice_checkout(request, *args, **kwargs):
    invoice_id = request.POST['product_id']
    invoice = Invoice.objects.select_related('student').get(pk=invoice_id)
    member = invoice.member
    if member and not member.is_ghost:
        if request.user != member:
            next_url = reverse('ikwen:sign_in')
            referrer = request.META.get('HTTP_REFERER')
            if referrer:
                next_url += '?' + urlquote(referrer)
            return HttpResponseRedirect(next_url)
    service = get_service_instance()
    config = service.config
    try:
        aggr = Payment.objects.filter(invoice=invoice, is_confirmed=True).aggregate(Sum('amount'))
        amount_paid = aggr['amount__sum']
    except IndexError:
        amount_paid = 0
    amount = invoice.amount - amount_paid
    model_name = 'billing.Invoice'

    mean = request.GET.get('mean', MTN_MOMO)
    tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS)\
        .create(service_id=service.id, type=MoMoTransaction.CASH_OUT, amount=amount, phone='N/A',
                model=model_name, object_id=invoice_id, wallet=mean, username=request.user.username, is_running=True)
    notification_url = service.url + reverse('foulassi:confirm_invoice_payment', args=(tx.id, ))
    cancel_url = service.url + reverse('billing:invoice_detail', args=(invoice_id, ))
    return_url = service.url + reverse('billing:invoice_detail', args=(invoice_id, ))
    gateway_url = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_URL', 'https://payment.ikwen.com')
    endpoint = gateway_url + '/request_payment'
    params = {
        'username': getattr(settings, 'IKWEN_PAYMENT_GATEWAY_USERNAME', 'arch'),
        'amount': amount,
        'merchant_name': config.company_name,
        'notification_url': notification_url,
        'return_url': return_url,
        'cancel_url': cancel_url,
        'user_id': request.user.username
    }
    r = requests.get(endpoint, params)
    next_url = gateway_url + '/checkoutnow/' + r.json()['token'] + '?mean=' + mean
    return HttpResponseRedirect(next_url)


def confirm_invoice_payment(request, *args, **kwargs):
    status = request.GET['status']
    message = request.GET['message']
    operator_tx_id = request.GET['operator_tx_id']
    phone = request.GET['phone']
    tx_id = kwargs['tx_id']
    try:
        tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS).get(pk=tx_id)
        tx_timeout = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_TIMEOUT', 15) * 60
        expiry = tx.created_on + timedelta(seconds=tx_timeout)
        if datetime.now() > expiry:
            return HttpResponse("Transaction %s timed out." % tx_id)
    except:
        raise Http404("Transaction %s not found" % tx_id)
    tx.status = status
    tx.message = message
    tx.processor_tx_id = operator_tx_id
    tx.phone = phone
    tx.is_running = False
    tx.save()
    if status != MoMoTransaction.SUCCESS:
        return HttpResponse("Notification for transaction %s received with status %s" % (tx_id, status))
    invoice = Invoice.objects.get(pk=tx.object_id)
    Payment.objects.create(invoice=invoice, method=Payment.MOBILE_MONEY,
                           amount=tx.amount, processor_tx_id=operator_tx_id)
    invoice.paid = invoice.amount
    invoice.status = Invoice.PAID
    invoice.save()
    service = get_service_instance()
    school = service.config
    if not school.is_public or (school.is_public and not invoice.is_tuition):
        service.raise_balance(tx.amount, provider=tx.wallet)

    return HttpResponse("Notification for transaction %s received with status %s" % (tx_id, status))
