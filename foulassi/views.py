import json
import logging
from collections import OrderedDict
from datetime import datetime, timedelta
from threading import Thread

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http.response import HttpResponseRedirect, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.utils.http import urlunquote
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.generic import TemplateView
from django.utils.translation import gettext as _, activate

from ikwen.core.generic import ChangeObjectBase
from ikwen.conf.settings import MEDIA_URL, MEMBER_AVATAR
from ikwen.core.constants import MALE, FEMALE
from ikwen.core.models import Application, Service
from ikwen.core.utils import add_database, get_service_instance, get_mail_content, send_sms, send_push
from ikwen.core.views import HybridListView
from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import Member
from ikwen.accesscontrol.utils import VerifiedEmailTemplateView
from ikwen.billing.models import CloudBillingPlan, IkwenInvoiceItem, InvoiceEntry
from ikwen.billing.utils import get_next_invoice_number
from ikwen.theming.models import Theme, Template
from ikwen.partnership.models import ApplicationRetailConfig
from ikwen_foulassi.foulassi.cloud_setup import DeploymentForm, deploy
from ikwen_foulassi.foulassi.utils import can_access_kid_detail

from ikwen_foulassi.foulassi.models import ParentProfile, Student, Invoice, Event, Parent, EventType, \
    PARENT_REQUEST_KID, KidRequest, Reminder, SchoolConfig, get_school_year
from ikwen_foulassi.school.models import get_subject_list, Justificatory, DisciplineLogEntry, Score, Assignment, \
    Homework
from ikwen_foulassi.school.models import AssignmentCorrection
from ikwen_foulassi.school.admin import HomeworkAdmin
from ikwen_foulassi.school.student.views import StudentDetail, ChangeJustificatory

logger = logging.getLogger('ikwen')

SCHOOL_WEBSITE_MONTH_COUNT = -1  # We agreed that invoice with month_count=-1 represents invoice for school website service purchase


class Home(TemplateView):
    template_name = 'foulassi/home.html'


class DownloadApp(TemplateView):
    """
    The page where parents will download on their Android smartphones the app.
    """
    template_name = 'foulassi/download_app.html'


class HomeSaaS(TemplateView):
    """
    Homepage of Foulassi addressed to schools presenting the Software as a Service
    """
    template_name = 'foulassi/home_saas.html'


class TermsAndConditions(TemplateView):
    template_name = 'foulassi/terms_and_conditions.html'


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

    def get_context_data(self, **kwargs):
        context = super(AdminHome, self).get_context_data(**kwargs)
        service = get_service_instance()
        db = service.database
        add_database(db)
        reminder_list = list(Reminder.objects.using(db).all())
        total_missing = 0
        for reminder in reminder_list:
            total_missing += reminder.missing
        if total_missing > 0:
            context['reminder_list'] = reminder_list
            context['total_missing'] = total_missing

        return context


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
                if student.school_year < get_school_year():
                    obj.delete()
                    continue
                if student.my_kids_expiry:
                    diff = student.my_kids_expiry - datetime.now()
                    if diff.total_seconds() <= 0:
                        student.my_kids_expired = True
                        student.save()
                else:
                    student.my_kids_expired = True
                    student.save()
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
        student = Student.objects.select_related('school').get(pk=student_id)
        db = student.school.database
        add_database(db)
        user.save(using=db)
        Parent.objects.using(db).filter(Q(email=user.email) | Q(phone=user.phone), student=student).update(member=user)
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
        student = Student.objects.select_related('school').get(pk=student_id)
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
            student = Student.objects.using(school.database).select_related('school', 'classroom').get(pk=student_id)
            if student.my_kids_expiry:
                diff = student.my_kids_expiry - datetime.now()
                if diff.total_seconds() <= 0:
                    student.my_kids_expired = True
                    student.save()
            else:
                student.my_kids_expired = True
                student.save()
            # if not student.mykids_fees_paid:
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
        now = datetime.now()
        end_year_date = datetime(day=31, month=8, year=get_school_year() + 1)
        month_expiry = now + timedelta(days=30)
        term_expiry = now + timedelta(days=90)
        # kid_list.remove(student)
        context['kid_list'] = kid_list
        context['using'] = db
        parent1 = Parent.objects.filter(student=student)[0]
        context['is_first_parent'] = parent1.email == user.email or parent1.phone == user.phone
        context['has_pending_assignment'] = Assignment.objects.using(db).filter(classroom=student.classroom, deadline__lt=now)
        context['has_pending_invoice'] = Invoice.objects.using(db).filter(student=student, status=Invoice.PENDING).count() > 0
        context['has_pending_disc'] = DisciplineLogEntry.objects.using(db).filter(student=student, was_viewed=False).count() > 0
        context['has_new_score'] = Score.objects.using(db).filter(student=student, was_viewed=False).count() > 0
        context['month_expiry'] = min(month_expiry, end_year_date)
        context['term_expiry'] = min(term_expiry, end_year_date)
        context['year_expiry'] = end_year_date
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


class ChangeHomework(ChangeObjectBase):
    model = Homework
    model_admin = HomeworkAdmin
    template_name = 'foulassi/snippets/change_homework.html'

    def get_object_list_url(self, request, obj, *args, **kwargs):
        ikwen_name = kwargs['ikwen_name']
        student_id = kwargs['student_id']
        url = reverse("foulassi:kid_detail", args=(ikwen_name, student_id))
        return url + "?showTab=assignments"

    def get_object(self, **kwargs):
        ikwen_name = kwargs['ikwen_name']
        homework_id = kwargs.get('object_id')
        try:
            school = Service.objects.get(project_name_slug=ikwen_name)
            self.db = school.database
            add_database(self.db)
            # student = Student.objects.using(school.database).select_related('school', 'classroom').get(pk=student_id)
            if homework_id:
                return Homework.objects.using(self.db).get(pk=homework_id)
        except ObjectDoesNotExist:
            raise Http404("School or student or homework not found")

    def get_context_data(self, **kwargs):
        context = super(ChangeHomework, self).get_context_data(**kwargs)
        ikwen_name = kwargs['ikwen_name']
        student_id = kwargs['student_id']
        assignment_id = kwargs['assignment_id']
        student = Student.objects.using(self.db).get(pk=student_id)
        now = datetime.now()
        obj = context.get('obj')
        context['deadline_reached'] = False if not obj else (True if obj.assignment.deadline < now.date() else False)
        context['student'] = student
        context['assignment'] = Assignment.objects.using(self.db).get(pk=assignment_id)
        context['ikwen_name'] = ikwen_name
        return context

    def after_save(self, request, obj, *args, **kwargs):
        """"
        Notify the teacher when a student send his homework
        """
        try:
            foulassi = Service.objects.using(UMBRELLA).get(project_name_slug='foulassi')
        except:
            foulassi = None
        student = obj.student
        classroom = student.classroom
        assignment = obj.assignment
        assignment_subject = assignment.subject

        teacher = assignment_subject.get_teacher(classroom)  # Retrieve the teacher who gives assignment
        service = get_service_instance()
        school_config = service.config
        company_name = school_config.company_name
        classroom_name = classroom.name
        sender = '%s via ikwen Foulassi <no-reply@ikwen.com>' % student
        # try:
        #     # cta_url = 'https://go.ikwen.com' + reverse('foulassi:change_homework', args=(
        #     #     school_config.company_name_slug, student.pk, assignment.pk))
        # except:
        #     cta_url = ''

        if teacher.member:
            activate(teacher.member.language)
        student_name = student.first_name
        subject = _(" New homework sent")
        extra_context = {'subject': subject, 'teacher': teacher, 'school_name': company_name,
                         'student_name': student_name, 'assignment': assignment, 'classroom': classroom_name}

        try:
            html_content = get_mail_content(subject,
                                            template_name='foulassi/mails/submitted_homework.html',
                                            extra_context=extra_context)
            teacher_email = teacher.member.email
            msg = EmailMessage(subject, html_content, sender,
                               [teacher_email, 'rsihon@gmail.com', 'silatchomsiaka@gmail.com'])
            msg.content_subtype = "html"
            try:
                msg.send()
            except Exception as e:
                logger.debug(e.message)
        except:
            logger.error("Could not generate HTML content from template", exc_info=True)

        body = _("%(student_name)s from %(classroom)s sent his assignment of %(subject)s about %(assignment_name)s"
                 % {'student_name': student_name, 'classroom': classroom_name,
                    'subject': assignment_subject, 'assignment_name': assignment.title})
        send_push(foulassi, teacher.member, subject, body)


class DownloadCorrection(TemplateView):
    template_name = 'foulassi/snippets/download_correction.html'

    def get_context_data(self, **kwargs):
        context = super(DownloadCorrection, self).get_context_data(**kwargs)
        ikwen_name = kwargs['ikwen_name']
        school = Service.objects.get(project_name_slug=ikwen_name)
        db = school.database
        add_database(db)
        assignment = Assignment.objects.using(db).get(pk=kwargs['assignment_id'])
        context['assignment'] = assignment
        try:
            correction = AssignmentCorrection.objects.using(db).get(assignment=assignment)
            context['correction'] = correction
            context['extension'] = '.' + correction.attachment.name.split('.')[1]
            entry = '%s correction' % correction
            student = Student.objects.using(db).get(pk=kwargs['student_id'])
            invoice = Invoice.objects.get(member=self.request.member, student=student, school=school, entries=[entry])
            context['invoice'] = invoice
        except:
            pass
        context['ikwen_name'] = ikwen_name
        return context


class ShowJustificatory(ChangeJustificatory):
    template_name = 'foulassi/show_justificatory.html'

    def get_object(self, **kwargs):
        ikwen_name = kwargs['ikwen_name']
        object_id = kwargs['object_id']
        try:
            school = Service.objects.get(project_name_slug=ikwen_name)
            add_database(school.database)
            obj = Justificatory.objects.using(school.database).select_related('entry').get(pk=object_id)
            # if not student.mykids_fees_paid:
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
            partner_id = request.COOKIES.get('referrer')
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

            try:
                partner = Service.objects.using(UMBRELLA).get(pk=partner_id) if partner_id else None
            except:
                partner = None

            invoice_entries = []
            website_setup = IkwenInvoiceItem(label=_('Foulassi deployment'), price=billing_plan.setup_cost, amount=setup_cost)
            website_setup_entry = InvoiceEntry(item=website_setup, short_description=project_name, quantity=12, total=setup_cost)
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


class BuyWebsite(TemplateView):
    template_name = 'foulassi/buy_website.html'

    def get_context_data(self, **kwargs):
        context = super(BuyWebsite, self).get_context_data()
        service = get_service_instance()
        context['cost'] = 12000
        context['config'] = service.config
        context['service'] = service
        return context

    def get(self, request, *args, **kwargs):
        action = request.GET.get('action')
        if action == 'place_invoice':
            return self.place_invoice(request, *args, **kwargs)
        return super(BuyWebsite, self).get(request, *args, **kwargs)

    def place_invoice(self, request, *args, **kwargs):
        school_name = kwargs['school_name']
        weblet = Service.objects.get(project_name_slug=school_name)
        try:
            db = weblet.database
            add_database(db)
            school = SchoolConfig.objects.using(db).get(service=weblet)
            now = datetime.now()
            due_date = now + timedelta(days=7)
            number = get_next_invoice_number()
            from ikwen.billing.utils import Invoice
            app = Application.objects.using(UMBRELLA).get(slug='foulassi')
            cost = 12000
            item = IkwenInvoiceItem(label='School website', price=cost, amount=cost)
            entry = InvoiceEntry(item=item, total=cost)
            invoice_entries = [entry]
            try:
                Invoice.objects.using(UMBRELLA).get(subscription=weblet, months_count=SCHOOL_WEBSITE_MONTH_COUNT)
            except:
                invoice = Invoice(subscription=weblet, member=weblet.member, amount=cost,
                                  months_count=SCHOOL_WEBSITE_MONTH_COUNT, number=number,
                                  due_date=due_date, last_reminder=now, entries=invoice_entries, is_one_off=True)
                invoice.save()
            school.has_subscribed_website_service = True
            school.save()
            return HttpResponse(json.dumps({'success': True}, 'content-type: text/json'))
        except:
            return HttpResponse(json.dumps({'error': True}, 'content-type: text/json'))






