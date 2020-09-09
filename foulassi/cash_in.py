import logging
import random
import string
from datetime import timedelta, datetime

import requests
from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.db.models import Sum
from django.http.response import HttpResponseRedirect, Http404, HttpResponse
from django.utils.http import urlquote
from django.utils.translation import ugettext as _

from currencies.models import Currency
from ikwen.conf.settings import WALLETS_DB_ALIAS
from ikwen.core.models import Service
from ikwen.core.utils import add_database, get_service_instance, get_mail_content, XEmailMessage
from ikwen.billing.models import MoMoTransaction
from ikwen.billing.utils import get_payment_confirmation_message, generate_pdf_invoice, get_invoicing_config_instance, \
    get_billing_cycle_days_count
from ikwen.billing.mtnmomo.views import MTN_MOMO
from ikwen_foulassi.foulassi.utils import share_payment_and_set_stats
from ikwen_foulassi.foulassi.models import Invoice, Payment, SchoolConfig

logger = logging.getLogger('ikwen')


def set_invoice_checkout(request, *args, **kwargs):
    invoice_id = request.POST['product_id']
    invoice = Invoice.objects.select_related('school', 'student').get(pk=invoice_id)
    member = invoice.member
    if member and not member.is_ghost:
        if request.user != member:
            next_url = reverse('ikwen:sign_in')
            referrer = request.META.get('HTTP_REFERER')
            if referrer:
                next_url += '?' + urlquote(referrer)
            return HttpResponseRedirect(next_url)
    service = get_service_instance()
    school = invoice.school
    try:
        aggr = Payment.objects.filter(invoice=invoice).aggregate(Sum('amount'))
        amount_paid = aggr['amount__sum']
    except IndexError:
        amount_paid = 0

    amount = invoice.amount - amount_paid
    model_name = 'billing.Invoice'
    mean = request.GET.get('mean', MTN_MOMO)
    signature = ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits) for i in range(16)])
    MoMoTransaction.objects.using(WALLETS_DB_ALIAS).filter(object_id=invoice_id).delete()
    tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS)\
        .create(service_id=school.id, type=MoMoTransaction.CASH_OUT, amount=amount, phone='N/A', model=model_name,
                object_id=invoice_id, task_id=signature, wallet=mean, username=request.user.username, is_running=True)
    notification_url = service.url + reverse('foulassi:confirm_invoice_payment', args=(tx.id, signature))
    cancel_url = request.META['HTTP_REFERER']
    return_url = request.META['HTTP_REFERER']
    gateway_url = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_URL', 'http://payment.ikwen.com/v1')
    endpoint = gateway_url + '/request_payment'
    params = {
        'username': getattr(settings, 'IKWEN_PAYMENT_GATEWAY_USERNAME', service.project_name_slug),
        'amount': amount,
        'merchant_name': school.project_name,
        'notification_url': notification_url,
        'return_url': return_url,
        'cancel_url': cancel_url,
        'user_id': request.user.username
    }
    try:
        r = requests.get(endpoint, params)
        resp = r.json()
        token = resp.get('token')
        if token:
            next_url = gateway_url + '/checkoutnow/' + resp['token'] + '?mean=' + mean
        else:
            logger.error("%s - Init payment flow failed with URL %s and message %s" % (service.project_name, r.url, resp['errors']))
            messages.error(request, resp['errors'])
            next_url = cancel_url
    except:
        logger.error("%s - Init payment flow failed with URL." % service.project_name, exc_info=True)
        next_url = cancel_url
    return HttpResponseRedirect(next_url)


def confirm_invoice_payment(request, *args, **kwargs):
    status = request.GET['status']
    message = request.GET['message']
    operator_tx_id = request.GET['operator_tx_id']
    phone = request.GET['phone']
    tx_id = kwargs['tx_id']
    try:
        tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS).get(pk=tx_id)
        if not getattr(settings, 'DEBUG', False):
            tx_timeout = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_TIMEOUT', 15) * 60
            expiry = tx.created_on + timedelta(seconds=tx_timeout)
            if datetime.now() > expiry:
                return HttpResponse("Transaction %s timed out." % tx_id)
    except:
        raise Http404("Transaction %s not found" % tx_id)

    callback_signature = kwargs.get('signature')
    no_check_signature = request.GET.get('ncs')
    if getattr(settings, 'DEBUG', False):
        if not no_check_signature:
            if callback_signature != tx.task_id:
                return HttpResponse('Invalid transaction signature')
    else:
        if callback_signature != tx.task_id:
            return HttpResponse('Invalid transaction signature')

    if status != MoMoTransaction.SUCCESS:
        return HttpResponse("Notification for transaction %s received with status %s" % (tx_id, status))

    school = Service.objects.get(pk=tx.service_id)
    school_config = SchoolConfig.objects.get(service=school)
    ikwen_charges = tx.amount * school_config.ikwen_share_rate / 100

    tx.status = status
    tx.message = message
    tx.processor_tx_id = operator_tx_id
    tx.phone = phone
    tx.is_running = False
    tx.fees = ikwen_charges
    tx.save()
    mean = tx.wallet
    add_database(school.database)
    invoice = Invoice.objects.get(pk=tx.object_id)
    payment = Payment.objects.create(invoice=invoice, method=Payment.MOBILE_MONEY,
                                     amount=tx.amount, processor_tx_id=operator_tx_id)
    payment.save(using=school.database)
    invoice.paid = invoice.amount
    invoice.status = Invoice.PAID
    invoice.save()
    invoice.save(using=school.database)
    student = invoice.student
    if not school_config.is_public or (school_config.is_public and not invoice.is_tuition):
        amount = tx.amount - ikwen_charges
        school.raise_balance(amount, provider=mean)
    student.set_has_new(using=school.database)
    student.save(using='default')

    member = invoice.member
    if member.email:
        try:
            currency = Currency.active.default().symbol
        except:
            currency = school_config.currency_code
        invoice_url = school.url + reverse('billing:invoice_detail', args=(invoice.id,))
        subject, message, sms_text = get_payment_confirmation_message(payment, member)
        html_content = get_mail_content(subject, message, template_name='billing/mails/notice.html',
                                        extra_context={'member_name': member.first_name, 'invoice': invoice,
                                                       'cta': _("View invoice"), 'invoice_url': invoice_url,
                                                       'currency': currency})
        sender = '%s <no-reply@%s>' % (school_config.company_name, school.domain)
        msg = XEmailMessage(subject, html_content, sender, [member.email])
        msg.content_subtype = "html"
        bcc = [email.strip() for email in school_config.notification_email.split(',') if email.strip()]
        bcc += [school_config.contact_email, school.member.email]
        msg.bcc = list(set(bcc))
        try:
            invoicing_config = get_invoicing_config_instance()
            invoice_pdf_file = generate_pdf_invoice(invoicing_config, invoice)
            msg.attach_file(invoice_pdf_file)
        except:
            pass
    return HttpResponse("Notification for transaction %s received with status %s" % (tx_id, status))


def set_my_kids_payment(request, *args, **kwargs):
    invoice_id = request.POST['product_id']
    invoice = Invoice.objects.select_related('school', 'student').get(pk=invoice_id)
    member = invoice.member
    if member and not member.is_ghost:
        if request.user != member:
            next_url = reverse('ikwen:sign_in')
            referrer = request.META.get('HTTP_REFERER')
            if referrer:
                next_url += '?' + urlquote(referrer)
            return HttpResponseRedirect(next_url)
    service = get_service_instance()  # This is ikwen service itself
    school = invoice.school
    school_config = SchoolConfig.objects.get(service=school)

    # Transaction is hidden from school if ikwen collects 100%.
    # This is achieved by changing the service_id of transaction
    tx_service_id = school.id if school_config.my_kids_share_rate < 100 else service.id
    amount = invoice.amount
    model_name = 'billing.Invoice'
    mean = request.GET.get('mean', MTN_MOMO)
    signature = ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits) for i in range(16)])
    MoMoTransaction.objects.using(WALLETS_DB_ALIAS).filter(object_id=invoice_id).delete()

    tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS)\
        .create(service_id=tx_service_id, type=MoMoTransaction.CASH_OUT, amount=amount, phone='N/A', model=model_name,
                object_id=invoice_id, task_id=signature, wallet=mean, username=request.user.username, is_running=True)
    notification_url = service.url + reverse('foulassi:confirm_my_kids_payment', args=(tx.id, signature))
    cancel_url = request.META['HTTP_REFERER']
    return_url = request.META['HTTP_REFERER']
    gateway_url = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_URL', 'http://payment.ikwen.com/v1')
    endpoint = gateway_url + '/request_payment'
    params = {
        'username': getattr(settings, 'IKWEN_PAYMENT_GATEWAY_USERNAME', service.project_name_slug),
        'amount': amount,
        'merchant_name': 'MyKids',
        'notification_url': notification_url,
        'return_url': return_url,
        'cancel_url': cancel_url,
        'user_id': request.user.username
    }
    try:
        r = requests.get(endpoint, params)
        resp = r.json()
        token = resp.get('token')
        if token:
            next_url = gateway_url + '/checkoutnow/' + resp['token'] + '?mean=' + mean
        else:
            logger.error("%s - Init payment flow failed with URL %s and message %s" % (service.project_name, r.url, resp['errors']))
            messages.error(request, resp['errors'])
            next_url = cancel_url
    except:
        logger.error("%s - Init payment flow failed with URL." % service.project_name, exc_info=True)
        next_url = cancel_url
    return HttpResponseRedirect(next_url)


def confirm_my_kids_payment(request, *args, **kwargs):
    status = request.GET['status']
    message = request.GET['message']
    operator_tx_id = request.GET['operator_tx_id']
    phone = request.GET['phone']
    tx_id = kwargs['tx_id']
    try:
        tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS).get(pk=tx_id)
        if not getattr(settings, 'DEBUG', False):
            tx_timeout = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_TIMEOUT', 15) * 60
            expiry = tx.created_on + timedelta(seconds=tx_timeout)
            if datetime.now() > expiry:
                return HttpResponse("Transaction %s timed out." % tx_id)
    except:
        raise Http404("Transaction %s not found" % tx_id)

    callback_signature = kwargs.get('signature')
    no_check_signature = request.GET.get('ncs')
    if getattr(settings, 'DEBUG', False):
        if not no_check_signature:
            if callback_signature != tx.task_id:
                return HttpResponse('Invalid transaction signature')
    else:
        if callback_signature != tx.task_id:
            return HttpResponse('Invalid transaction signature')

    if status != MoMoTransaction.SUCCESS:
        return HttpResponse("Notification for transaction %s received with status %s" % (tx_id, status))

    school = Service.objects.get(pk=tx.service_id)
    school_config = SchoolConfig.objects.get(service=school)
    ikwen_charges = tx.amount * school_config.my_kids_share_rate / 100

    tx.status = status
    tx.message = message
    tx.processor_tx_id = operator_tx_id
    tx.phone = phone
    tx.is_running = False
    tx.fees = ikwen_charges
    tx.save()
    mean = tx.wallet
    add_database(school.database)
    invoice = Invoice.objects.get(pk=tx.object_id)
    payment = Payment.objects.create(invoice=invoice, method=Payment.MOBILE_MONEY,
                                     amount=tx.amount, processor_tx_id=operator_tx_id)
    payment.save(using=school.database)
    invoice.paid = invoice.amount
    invoice.status = Invoice.PAID
    invoice.save()
    invoice.save(using=school.database)
    student = invoice.student

    amount = tx.amount - ikwen_charges
    school.raise_balance(amount, provider=mean)

    if tx.amount >= school_config.my_kids_fees:  # Default fees is annual
        billing_cycle = Service.YEARLY
    elif tx.amount >= school_config.my_kids_fees_term:
        billing_cycle = Service.QUARTERLY
    else:
        billing_cycle = Service.MONTHLY
    days = get_billing_cycle_days_count(billing_cycle)
    if student.my_kids_expiry:
        expiry = student.my_kids_expiry + timedelta(days=days)
    else:
        expiry = datetime.now() + timedelta(days=days)
    student.my_kids_expiry = expiry
    student.save(using=school.database)
    
    student.set_has_new(using=school.database)
    student.save(using='default')

    share_payment_and_set_stats(invoice, mean)
    member = invoice.member
    if member.email:
        try:
            currency = Currency.active.default().symbol
        except:
            currency = school_config.currency_code
        invoice_url = school.url + reverse('billing:invoice_detail', args=(invoice.id,))
        subject, message, sms_text = get_payment_confirmation_message(payment, member)
        html_content = get_mail_content(subject, message, template_name='billing/mails/notice.html',
                                        extra_context={'member_name': member.first_name, 'invoice': invoice,
                                                       'cta': _("View invoice"), 'invoice_url': invoice_url,
                                                       'currency': currency})
        sender = '%s <no-reply@%s>' % (school_config.company_name, school.domain)
        msg = XEmailMessage(subject, html_content, sender, [member.email])
        msg.content_subtype = "html"
        try:
            invoicing_config = get_invoicing_config_instance()
            invoice_pdf_file = generate_pdf_invoice(invoicing_config, invoice)
            msg.attach_file(invoice_pdf_file)
        except:
            pass
    return HttpResponse("Notification for transaction %s received with status %s" % (tx_id, status))
