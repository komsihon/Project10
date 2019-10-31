import json
import logging
import random
import string
from collections import OrderedDict
from datetime import timedelta, datetime
from threading import Thread

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.db.models import Sum, Q
from django.http.response import HttpResponseRedirect, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.utils.http import urlquote, urlunquote
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.generic import TemplateView
from django.utils.translation import gettext as _, get_language

from ikwen.conf.settings import WALLETS_DB_ALIAS, MEDIA_URL, MEMBER_AVATAR
from ikwen.core.constants import MALE, FEMALE
from ikwen.core.models import Application, Service
from ikwen.core.utils import add_database, get_service_instance, get_mail_content, send_sms
from ikwen.core.views import HybridListView
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member
from ikwen.accesscontrol.utils import VerifiedEmailTemplateView
from ikwen.billing.models import MoMoTransaction, CloudBillingPlan, IkwenInvoiceItem, InvoiceEntry
from ikwen.billing.mtnmomo.views import MTN_MOMO
from ikwen.theming.models import Theme, Template
from ikwen.partnership.models import ApplicationRetailConfig
from ikwen_foulassi.foulassi.cloud_setup import DeploymentForm, deploy
from ikwen_foulassi.foulassi.utils import can_access_kid_detail

from ikwen_foulassi.foulassi.models import ParentProfile, Student, Invoice, Payment, Event, Parent, EventType, \
    PARENT_REQUEST_KID, KidRequest, SchoolConfig
from ikwen_foulassi.school.models import get_subject_list, Justificatory

from ikwen_foulassi.school.student.views import StudentDetail, ChangeJustificatory

logger = logging.getLogger('ikwen')


class Home(TemplateView):
    template_name = 'foulassi/home.html'


class HomeSaaS(TemplateView):
    """
    Homepage of Foulassi addressed to schools presenting the Software as a Service
    """
    template_name = 'foulassi/home_saas.html'


class AdminHome(TemplateView):
    """
    Homepage of Foulassi admin
    """
    template_name = 'foulassi/admin_home.html'

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        user = request.user
        if action == 'get_in':
            challenge = request.GET.get('challenge')
            challenge = urlunquote(challenge)
            school = get_service_instance()
            if school.api_signature == challenge:
                if user.is_authenticated():
                    logout(request)
                member = authenticate(api_signature=challenge)
                login(request, member)
                next_url = reverse('school:subject_list') + '?first_setup=yes'
                return HttpResponseRedirect(next_url)
        elif user.is_anonymous() or (user.is_authenticated() and not user.is_staff):
            if user.is_authenticated():
                logout(request)
            next_url = reverse('ikwen:sign_in') + '?next=' + reverse('foulassi:admin_home')
            return HttpResponseRedirect(next_url)
        return super(AdminHome, self).get(request, *args, **kwargs)


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
        suggestion_key = 'kid_list:suggestion_list:' + user.username
        suggestion_list = cache.get(suggestion_key)
        if suggestion_list is None:
            suggestion_list = []
            for obj in Parent.objects.select_related('student').filter(Q(email=user.email) | Q(phone=user.phone)):
                student = obj.student
                if student.id in parent_profile.student_fk_list or student in suggestion_list:
                    continue
                try:
                    suggestion_list.append(student)
                except:
                    pass
            cache.set(suggestion_key, suggestion_list, 5 * 60)
        min_search_chars = 0
        try:
            app = Application.objects.get(slug='foulassi')
            school_count = Service.objects.filter(app=app).count()
            min_search_chars = len(str(school_count)) - 2
        except:
            pass
        context['suggestion_list'] = suggestion_list
        context['kid_list'] = kid_list
        context['min_search_chars'] = min_search_chars
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
        parent_profile, update = ParentProfile.objects.get_or_create(member=user)
        if student_id not in parent_profile.student_fk_list:
            parent_profile.student_fk_list.insert(0, student_id)
            parent_profile.save()
            suggestion_key = 'kid_list:suggestion_list:' + user.username
            fragment_key = make_template_fragment_key('kid_list', [user.username])
            cache.delete(suggestion_key)
            cache.delete(fragment_key)
        return HttpResponse(json.dumps({'success': True}, 'content-type: text/json'))

    def refuse_suggestion(self, request):
        user = request.user
        student_id = request.GET['student_id']
        student = Student.objects.get(pk=student_id)
        db = student.school.database
        add_database(db)
        Parent.objects.using(db).filter(Q(email=user.email) | Q(phone=user.phone), student=student).delete()
        suggestion_key = 'kid_list:suggestion_list:' + user.username
        fragment_key = make_template_fragment_key('kid_list', [user.username])
        cache.delete(suggestion_key)
        cache.delete(fragment_key)
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
        context['pending_invoice_count'] = Invoice.objects.using(db).filter(student=student, status=Invoice.PENDING).count()
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


class SearchSchool(HybridListView):
    template_name = 'foulassi/search_school.html'
    search_field = 'project_name_slug'

    def get_queryset(self, **kwargs):
        app = Application.objects.get(slug='foulassi')
        queryset = Service.objects.filter(app=app)
        if not getattr(settings, 'DEBUG', False):
            queryset = queryset.exclude(project_name_slug='foulassi')
        return queryset

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'invite_school':  # Send a request to see his children online to the school
            service = get_service_instance()
            member = request.user
            school_id = request.GET['school_id']
            kids_details = request.GET['kids_details']
            school = Service.objects.get(pk=school_id)
            db = school.database
            add_database(db)
            event_type, change = EventType.objects.using(db) \
                .get_or_create(codename=PARENT_REQUEST_KID, renderer='ikwen_foulassi.foulassi.events.render_parent_request_kid')
            kid_request = KidRequest.objects.using(db).create(parent=member, kids_details=kids_details)
            Event.objects.using(db).create(type=event_type, object_id_list=[kid_request.id])
            try:
                if member.gender == FEMALE:
                    parent_name = _("Mrs %s" % member.full_name)
                elif member.gender == MALE:
                    parent_name = _("Mr %s" % member.full_name)
                else:  # Unknown gender
                    parent_name = _("The parent %s" % member.full_name)
                subject = _("I would like to follow my kids in your school on Foulassi.")
                cta_url = school.url + reverse('foulassi:event_list')
                html_content = get_mail_content(subject, template_name='foulassi/mails/invite_school.html',
                                                extra_context={'parent': member, 'kids_details': kids_details,
                                                               'IKWEN_MEDIA_URL': MEDIA_URL, 'MEMBER_AVATAR': MEMBER_AVATAR,
                                                               'cta_url': cta_url})
                sender = '%s via ikwen Foulassi <no-reply@%s>' % (parent_name, service.domain)
                msg = EmailMessage(subject, html_content, sender, [school.config.contact_email.strip()])
                msg.content_subtype = "html"
                msg.cc = ["contact@ikwen.com"]
                if member.email:
                    msg.extra_headers = {'Reply-To': member.email}
                Thread(target=lambda m: m.send(), args=(msg,)).start()
                sms_text = _("%(parent_name)s would like to follow his kid(s) below on ikwen Foulassi:\n"
                             "%(kids_details)s" % {'parent_name': parent_name, 'kids_details': kids_details})
                if member.phone:
                    if len(member.phone) == 9:
                        member.phone = '237' + member.phone
                    send_sms(member.phone, sms_text)
            except:
                pass
            return HttpResponse(json.dumps({'success': True}, 'content-type: text/json'))
        return super(SearchSchool, self).get(request, *args, **kwargs)


def set_invoice_checkout(request, *args, **kwargs):
    invoice_id = request.POST['product_id']
    invoice = Invoice.objects.select_related('school, student').get(pk=invoice_id)
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
    lang = get_language()
    tx = MoMoTransaction.objects.using(WALLETS_DB_ALIAS)\
        .create(service_id=school.id, type=MoMoTransaction.CASH_OUT, amount=amount, phone='N/A', model=model_name,
                object_id=invoice_id, task_id=signature, wallet=mean, username=request.user.username, is_running=True)
    notification_url = service.url + reverse('foulassi:confirm_invoice_payment', args=(tx.id, signature, lang))
    cancel_url = request.META['HTTP_REFERER']
    return_url = request.META['HTTP_REFERER']
    gateway_url = getattr(settings, 'IKWEN_PAYMENT_GATEWAY_URL', 'https://payment.ikwen.com/v1')
    endpoint = gateway_url + '/request_payment'
    params = {
        'username': getattr(settings, 'IKWEN_PAYMENT_GATEWAY_USERNAME', service.project_name_slug),
        'amount': amount,
        'merchant_name': config.company_name,
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
            messages.error(resp['errors'])
            next_url = cancel_url
    except:
        logger.error("%s - Init payment flow failed with URL %s." % (service.project_name, r.url), exc_info=True)
        next_url = cancel_url
    return HttpResponseRedirect(next_url)
    # try:
    #     r = requests.get(endpoint, params)
    #     resp = r.json()
    #     token = resp.get('token')
    #     if token:
    #         payment_url = gateway_url + '/checkoutnow/' + resp['token'] + '?mean=' + mean
    #         return render(request, template_name='billing/gateway.html', context={'payment_url': payment_url})
    #     else:
    #         messages.error(request, resp['errors'])
    #         return HttpResponseRedirect(cancel_url)
    # except:
    #     logger.error("%s - Init payment flow failed with URL %s." % (service.project_name, r.url), exc_info=True)
    #     messages.error(request, "Init payment flow failed.")
    #     return HttpResponseRedirect(cancel_url)


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

    tx.status = status
    tx.message = message
    tx.processor_tx_id = operator_tx_id
    tx.phone = phone
    tx.is_running = False
    tx.save()
    school = Service.objects.get(pk=tx.service_id)
    school_config = SchoolConfig.objects.get(service=school)
    add_database(school.database)
    invoice = Invoice.objects.get(pk=tx.object_id)
    payment = Payment.objects.create(invoice=invoice, method=Payment.MOBILE_MONEY,
                                     amount=tx.amount, processor_tx_id=operator_tx_id)
    payment.save(using=school.database)
    invoice.paid = invoice.amount
    invoice.status = Invoice.PAID
    invoice.save()
    invoice.save(using=school.database)
    if not school_config.is_public or (school_config.is_public and not invoice.is_tuition):
        if invoice.is_my_kids:
            amount = tx.amount * (100 - school_config.ikwen_share_rate) / 100
        else:
            amount = tx.amount
        school.raise_balance(amount, provider=tx.wallet)
    student = invoice.student
    student.set_has_new(using=school.database)
    student.save(using='default')
    return HttpResponse("Notification for transaction %s received with status %s" % (tx_id, status))


class DeployCloud(VerifiedEmailTemplateView):
    template_name = 'foulassi/cloud_setup/deploy.html'
    DEFAULT_THEME = 'foulassi'

    def get_context_data(self, **kwargs):
        context = super(DeployCloud, self).get_context_data(**kwargs)
        context['billing_cycles'] = Service.BILLING_CYCLES_CHOICES
        app = Application.objects.using(UMBRELLA).get(slug='foulassi')
        if getattr(settings, 'IS_IKWEN', False):
            billing_plan_list = CloudBillingPlan.objects.using(UMBRELLA).filter(app=app, partner__isnull=True, is_active=True)
            if billing_plan_list.count() == 0:
                context['ikwen_setup_cost'] = app.base_monthly_cost * 12
                context['ikwen_monthly_cost'] = app.base_monthly_cost
        else:
            service = get_service_instance()
            billing_plan_list = CloudBillingPlan.objects.using(UMBRELLA).filter(app=app, partner=service, is_active=True)
            if billing_plan_list.count() == 0:
                retail_config = ApplicationRetailConfig.objects.using(UMBRELLA).get(app=app, partner=service)
                context['ikwen_setup_cost'] = retail_config.ikwen_monthly_cost * 12
                context['ikwen_monthly_cost'] = retail_config.ikwen_monthly_cost
        if billing_plan_list.count() > 0:
            context['billing_plan'] = billing_plan_list[0]
        return context


    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def post(self, request, *args, **kwargs):
        form = DeploymentForm(request.POST)
        if form.is_valid():
            project_name = form.cleaned_data.get('project_name')
            billing_plan_id = form.cleaned_data.get('billing_plan_id')
            partner_id = form.cleaned_data.get('partner_id')
            webnode = Application.objects.get(slug='webnode')
            template_list = list(Template.objects.filter(app=webnode))
            try:
                theme = Theme.objects.using(UMBRELLA).get(template__in=template_list, slug=self.DEFAULT_THEME)
            except:
                theme = None
                logger.error("Foulassi deployment: %s webnode theme not found" % self.DEFAULT_THEME)
            billing_plan = CloudBillingPlan.objects.using(UMBRELLA).get(pk=billing_plan_id)

            is_ikwen = getattr(settings, 'IS_IKWEN', False)
            if not is_ikwen or (is_ikwen and request.user.is_staff):
                customer_id = form.cleaned_data.get('customer_id')
                if not customer_id:
                    customer_id = request.user.id
                customer = Member.objects.using(UMBRELLA).get(pk=customer_id)
                setup_cost = form.cleaned_data.get('setup_cost')
                monthly_cost = form.cleaned_data.get('monthly_cost')
                if setup_cost < billing_plan.setup_cost:
                    return HttpResponseForbidden("Attempt to set a Setup cost lower than allowed.")
                if monthly_cost < billing_plan.monthly_cost:
                    return HttpResponseForbidden("Attempt to set a monthly cost lower than allowed.")
            else:
                # User self-deploying his website
                customer = Member.objects.using(UMBRELLA).get(pk=request.user.id)
                setup_cost = billing_plan.setup_cost
                monthly_cost = billing_plan.monthly_cost

            partner = Service.objects.using(UMBRELLA).get(pk=partner_id) if partner_id else None

            invoice_entries = []
            website_setup = IkwenInvoiceItem(label=_('Foulassi deployment'), price=billing_plan.setup_cost, amount=setup_cost)
            website_setup_entry = InvoiceEntry(item=website_setup, short_description=project_name, total=setup_cost)
            invoice_entries.append(website_setup_entry)
            if theme and theme.cost > 0:
                theme_item = IkwenInvoiceItem(label=_('Website theme'), price=theme.cost, amount=theme.cost)
                theme_entry = InvoiceEntry(item=theme_item, short_description=theme.name, total=theme.cost)
                invoice_entries.append(theme_entry)
            if getattr(settings, 'DEBUG', False):
                service = deploy(customer, project_name, billing_plan, theme, monthly_cost, invoice_entries, partner)
            else:
                try:
                    service = deploy(customer, project_name, billing_plan, theme, monthly_cost, invoice_entries, partner)
                except Exception as e:
                    logger.error("Foulassi deployment failed for %s" % project_name, exc_info=True)
                    context = self.get_context_data(**kwargs)
                    context['errors'] = e.message
                    return render(request, 'foulassi/cloud_setup/deploy.html', context)
            if is_ikwen:
                if request.user.is_staff:
                    next_url = reverse('partnership:change_service', args=(service.id,))
                else:
                    next_url = reverse('foulassi:successful_deployment', args=(service.ikwen_name,))
            else:
                next_url = reverse('change_service', args=(service.id,))
            return HttpResponseRedirect(next_url)
        else:
            context = self.get_context_data(**kwargs)
            context['errors'] = form.errors
            return render(request, 'foulassi/cloud_setup/deploy.html', context)


class SuccessfulDeployment(VerifiedEmailTemplateView):
    template_name = 'foulassi/cloud_setup/successful_deployment.html'

    def get_context_data(self, **kwargs):
        context = super(SuccessfulDeployment, self).get_context_data(**kwargs)
        ikwen_name = kwargs['ikwen_name']
        school = Service.objects.get(project_name_slug=ikwen_name)
        context['school'] = school
        return context

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        school = context['school']
        if school.member != request.user:
            return HttpResponseForbidden("You're not allowed here")
        return render(request, self.template_name, context)
