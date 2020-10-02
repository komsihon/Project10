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
from ikwen.billing.models import MoMoTransaction, InvoiceItem, InvoiceEntry
from ikwen.billing.utils import get_payment_confirmation_message, generate_pdf_invoice, get_invoicing_config_instance, \
    get_billing_cycle_days_count, get_next_invoice_number
from ikwen.billing.mtnmomo.views import MTN_MOMO
from ikwen_foulassi.foulassi.utils import share_payment_and_set_stats
from ikwen_foulassi.foulassi.models import Invoice, Payment, SchoolConfig, Student

logger = logging.getLogger('ikwen')


def set_invoice_checkout(request, *args, **kwargs):
    invoice_id = request.POST['product_id']
    school_id = request.POST['school_id']
    school = Service.objects.get(pk=school_id)
    db = school.database
    add_database(db)
    invoice = Invoice.objects.using(db).select_related('school', 'student').get(pk=invoice_id)
    member = invoice.member
    if member and not member.is_ghost:
        if request.user != member:
            next_url = reverse('ikwen:sign_in')
            referrer = request.META.get('HTTP_REFERER')
            if referrer:
                next_url += '?' + urlquote(referrer)
            return HttpResponseRedirect(next_url)
    service = get_service_instance()
    try:
        aggr = Payment.objects.using(db).filter(invoice=invoice).aggregate(Sum('amount'))
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
    db = school.database
    add_database(db)
    invoice = Invoice.objects.using(db).get(pk=tx.object_id)
    payment = Payment.objects.using(db).create(invoice=invoice, method=Payment.MOBILE_MONEY,
                                               amount=tx.amount, processor_tx_id=operator_tx_id)
    invoice.paid = tx.amount
    invoice.status = Invoice.PAID
    invoice.save()
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
        bcc = [email.strip() for email in school_config.notification_emails.split(',') if email.strip()]
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
    school_id = request.POST['school_id']
    student_id = request.POST['student_id']
    cycle = request.POST['my_kids_cycle']
    school = Service.objects.get(pk=school_id)
    student = Student.objects.get(pk=student_id)
    school_config = SchoolConfig.objects.get(school=school)
    Invoice.objects.filter(student=student, is_my_kids=True, status=Invoice.PENDING).delete()
    if cycle == Service.YEARLY:
        amount = school_config.my_kids_fees
    elif cycle == Service.QUARTERLY:
        amount = school_config.my_kids_fees_term
    else:
        amount = school_config.my_kids_fees_month
        cycle = Service.MONTHLY
    item = InvoiceItem(label=_("MyKids fees"), amount=amount)
    days = get_billing_cycle_days_count(cycle)
    now = datetime.now()
    expiry = now + timedelta(days=days)
    short_description = now.strftime("%Y/%m/%d") + ' - ' + expiry.strftime("%Y/%m/%d")
    entry = InvoiceEntry(item=item, short_description=short_description, total=amount, quantity_unit='')
    number = get_next_invoice_number()
    member = request.user
    invoice = Invoice.objects.create(number=number, member=member, student=student, school=school, is_one_off=True,
                                     amount=amount, my_kids_cycle=cycle, due_date=now, entries=[entry], is_my_kids=True)
    foulassi_weblet = get_service_instance()  # This is Foulassi service itself

    # Transaction is hidden from school if ikwen collects 100%.
    # This is achieved by changing the service_id of transaction
    tx_service_id = school.id if school_config.my_kids_share_rate < 100 else foulassi_weblet.id
    model_name = 'billing.Invoice'
    mean = request.GET.get('mean', MTN_MOMO)
    signature = ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits) for i in range(16)])
    MoMoTransaction.objects.using(WALLETS_DB_ALIAS).filter(object_id=invoice.id).delete()

    tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS)\
        .create(service_id=tx_service_id, type=MoMoTransaction.CASH_OUT, amount=amount, phone='N/A', model=model_name,
                object_id=invoice.id, task_id=signature, wallet=mean, username=request.user.username, is_running=True)
    notification_url = foulassi_weblet.url + reverse('foulassi:confirm_my_kids_payment', args=(tx.id, signature))
    cancel_url = request.META['HTTP_REFERER']
    return_url = request.META['HTTP_REFERER']
    gateway_url = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_URL', 'http://payment.ikwen.com/v1')
    endpoint = gateway_url + '/request_payment'
    params = {
        'username': getattr(settings, 'IKWEN_PAYMENT_GATEWAY_USERNAME', foulassi_weblet.project_name_slug),
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
            logger.error("%s - Init payment flow failed with URL %s and message %s" % (foulassi_weblet.project_name, r.url, resp['errors']))
            messages.error(request, resp['errors'])
            next_url = cancel_url
    except:
        logger.error("%s - Init payment flow failed with URL." % foulassi_weblet.project_name, exc_info=True)
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

    invoice = Invoice.objects.get(pk=tx.object_id)
    school = invoice.school
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

    amount = tx.amount - ikwen_charges
    school.raise_balance(amount, provider=mean)
    share_payment_and_set_stats(invoice, mean)

    invoice.paid = invoice.amount
    invoice.status = Invoice.PAID
    invoice.save()

    member = invoice.member
    student = invoice.student
    days = get_billing_cycle_days_count(invoice.my_kids_cycle)
    expiry = datetime.now() + timedelta(days=days)
    student.my_kids_expiry = expiry
    student.save()

    db = school.database
    add_database(db)
    invoice.save(using=db)
    payment = Payment(invoice=invoice, method=Payment.MOBILE_MONEY, amount=tx.amount, processor_tx_id=operator_tx_id)
    if school_config.my_kids_share_rate < 100:
        # Payment appears in school log panel only if the have something to collect out of that
        payment.save(using=db)

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
