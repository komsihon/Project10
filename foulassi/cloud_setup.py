# -*- coding: utf-8 -*-
import os
import shutil
import string
import subprocess
from datetime import datetime, timedelta
from random import random
from threading import Thread

from django import forms
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.mail import EmailMessage
from django.core.urlresolvers import reverse
from django.template import Context
from django.template.defaultfilters import slugify
from django.template.loader import get_template
from django.utils.translation import gettext as _
from ikwen_kakocase.kako.models import Product
from ikwen_kakocase.kakocase.models import OperatorProfile, DeliveryOption
from permission_backend_nonrel.models import UserPermissionList, GroupPermissionList

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.accesscontrol.models import SUDO, Member
from ikwen.billing.models import Invoice, PaymentMean, InvoicingConfig, SupportCode
from ikwen.billing.utils import get_next_invoice_number
from ikwen.conf.settings import STATIC_ROOT, STATIC_URL, CLUSTER_MEDIA_ROOT, CLUSTER_MEDIA_URL, WALLETS_DB_ALIAS
from ikwen.core.models import Service, OperatorWallet, SERVICE_DEPLOYED
from ikwen.core.tools import generate_django_secret_key, generate_random_key, reload_server
from ikwen.core.utils import add_database_to_settings, add_event, get_mail_content, \
    get_service_instance
from ikwen.flatpages.models import FlatPage
from ikwen.partnership.models import PartnerProfile
from ikwen.theming.models import Template, Theme

from echo.models import Balance

import logging
logger = logging.getLogger('ikwen')


if getattr(settings, 'LOCAL_DEV', False):
    CLOUD_HOME = '/home/komsihon/PycharmProjects/CloudTest/'
else:
    CLOUD_HOME = '/home/ikwen/Cloud/'

CLOUD_FOLDER = CLOUD_HOME + 'Kakocase/'
SMS_API_URL = 'http://websms.mobinawa.com/http_api?action=sendsms&username=675187705&password=depotguinness&from=$label&to=$recipient&msg=$text'


# from captcha.fields import ReCaptchaField


class DeploymentForm(forms.Form):
    """
    Deployment form of a platform
    """
    partner_id = forms.CharField(max_length=24, required=False)  # Service ID of the partner retail platform
    app_id = forms.CharField(max_length=24)
    customer_id = forms.CharField(max_length=24)
    project_name = forms.CharField(max_length=30)
    domain = forms.CharField(max_length=60, required=False)
    business_type = forms.CharField(max_length=60)
    billing_cycle = forms.CharField(max_length=24)
    billing_plan_id = forms.CharField(max_length=24, required=False)
    business_category_id = forms.CharField(max_length=24, required=False)
    bundle_id = forms.CharField(max_length=24, required=False)
    setup_cost = forms.FloatField(required=False)
    monthly_cost = forms.FloatField(required=False)
    theme_id = forms.CharField()


def deploy(app, member, business_type, project_name, billing_plan, theme, monthly_cost, invoice_entries,
           billing_cycle, domain=None, business_category=None, bundle=None, partner_retailer=None):
    project_name_slug = slugify(project_name)  # Eg: slugify('Cool Shop') = 'cool-shop'
    ikwen_name = project_name_slug.replace('-', '')  # Eg: cool-shop --> 'coolshop'
    pname = ikwen_name
    i = 0
    while True:
        try:
            Service.objects.using(UMBRELLA).get(project_name_slug=pname)
            i += 1
            pname = "%s%d" % (ikwen_name, i)
        except Service.DoesNotExist:
            ikwen_name = pname
            break
    api_signature = generate_random_key(30)
    while True:
        try:
            Service.objects.using(UMBRELLA).get(api_signature=api_signature)
            api_signature = generate_random_key(30)
        except Service.DoesNotExist:
            break
    database = ikwen_name
    domain = 'go.' + pname + '.ikwen.com'
    domain_type = Service.SUB
    is_naked_domain = False
    url = 'http://go.ikwen.com/' + pname
    if getattr(settings, 'IS_UMBRELLA', False):
        admin_url = url + '/ikwen' + reverse('ikwen:staff_router')
    else:  # This is a deployment performed by a partner retailer
        admin_url = url + reverse('ikwen:staff_router')
    is_pro_version = billing_plan.is_pro_version
    now = datetime.now()
    expiry = now + timedelta(days=15)

    # Create a copy of template application in the Cloud folder
    app_folder = CLOUD_HOME + '000Tpl/AppSkeleton'
    website_home_folder = CLOUD_FOLDER + ikwen_name
    media_root = CLUSTER_MEDIA_ROOT + ikwen_name + '/'
    media_url = CLUSTER_MEDIA_URL + ikwen_name + '/'
    default_images_folder = CLOUD_FOLDER + '000Tpl/images/000Default'
    theme_images_folder = CLOUD_FOLDER + '000Tpl/images/%s/%s' % (theme.template.slug, theme.slug)
    if os.path.exists(theme_images_folder):
        if os.path.exists(media_root):
            shutil.rmtree(media_root)
        shutil.copytree(theme_images_folder, media_root)
        logger.debug("Media folder '%s' successfully created from '%s'" % (media_root, theme_images_folder))
    elif os.path.exists(default_images_folder):
        if os.path.exists(media_root):
            shutil.rmtree(media_root)
        shutil.copytree(default_images_folder, media_root)
        logger.debug("Media folder '%s' successfully created from '%s'" % (media_root, default_images_folder))
    elif not os.path.exists(media_root):
        os.makedirs(media_root)
        logger.debug("Media folder '%s' successfully created empty" % media_root)
    favicons_folder = media_root + 'favicons'
    if not os.path.exists(favicons_folder):
        os.makedirs(favicons_folder)
    if os.path.exists(website_home_folder):
        shutil.rmtree(website_home_folder)
    shutil.copytree(app_folder, website_home_folder)
    logger.debug("Service folder '%s' successfully created" % website_home_folder)

    can_manage_delivery_options = False
    if business_type == OperatorProfile.PROVIDER:
        settings_template = 'kakocase/cloud_setup/settings.provider.html'
        can_manage_delivery_options = True
    elif business_type == OperatorProfile.RETAILER:
        settings_template = 'kakocase/cloud_setup/settings.retailer.html'
    elif business_type == OperatorProfile.LOGISTICS:
        settings_template = 'kakocase/cloud_setup/settings.delivery.html'
        auth_code = ikwen_name[:4] + now.strftime('%S')
    elif business_type == OperatorProfile.BANK:
        settings_template = 'kakocase/cloud_setup/settings.bank.html'

    service = Service(member=member, app=app, project_name=project_name, project_name_slug=ikwen_name, domain=domain,
                      database=database, url=url, domain_type=domain_type, expiry=expiry,
                      admin_url=admin_url, billing_plan=billing_plan, billing_cycle=billing_cycle,
                      monthly_cost=monthly_cost, version=Service.TRIAL, retailer=partner_retailer,
                      api_signature=api_signature, home_folder=website_home_folder,
                      settings_template=settings_template)
    service.save(using=UMBRELLA)
    logger.debug("Service %s successfully created" % pname)

    if business_type == OperatorProfile.RETAILER:
        # Copy Categories image to local media folder as the Retailer is allowed to change them
        pass

    # Re-create settings.py file as well as apache.conf file for the newly created project
    secret_key = generate_django_secret_key()
    if is_naked_domain:
        allowed_hosts = '"%s", "www.%s"' % (domain, domain)
    else:
        allowed_hosts = '"go.ikwen.com"'
    settings_tpl = get_template(settings_template)
    settings_context = Context({'secret_key': secret_key, 'ikwen_name': ikwen_name, 'service': service,
                                'static_root': STATIC_ROOT, 'static_url': STATIC_URL,
                                'media_root': media_root, 'media_url': media_url,
                                'allowed_hosts': allowed_hosts, 'debug': getattr(settings, 'DEBUG', False)})
    settings_file = website_home_folder + '/conf/settings.py'
    fh = open(settings_file, 'w')
    fh.write(settings_tpl.render(settings_context))
    fh.close()
    logger.debug("Settings file '%s' successfully created" % settings_file)

    # Import template database and set it up
    if business_type == OperatorProfile.BANK:
        db_folder = CLOUD_FOLDER + '000Tpl/DB/CashFlex'
    else:
        db_folder = CLOUD_FOLDER + '000Tpl/DB/000Default'
        theme_db_folder = CLOUD_FOLDER + '000Tpl/DB/%s/%s' % (theme.template.slug, theme.slug)
        if os.path.exists(theme_db_folder):
            db_folder = theme_db_folder

    host = getattr(settings, 'DATABASES')['default'].get('HOST', '127.0.0.1')
    subprocess.call(['mongorestore', '--host', host, '-d', database, db_folder])
    logger.debug("Database %s successfully created on host %s from %s" % (database, host, db_folder))

    add_database_to_settings(database)
    for group in Group.objects.using(database).all():
        try:
            gpl = GroupPermissionList.objects.using(database).get(group=group)
            group.delete()
            group.save(using=database)   # Recreate the group in the service DB with a new id.
            gpl.group = group    # And update GroupPermissionList object with the newly re-created group
            gpl.save(using=database)
        except GroupPermissionList.DoesNotExist:
            group.delete()
            group.save(using=database)  # Re-create the group in the service DB with anyway.
    new_sudo_group = Group.objects.using(database).get(name=SUDO)

    for s in member.get_services():
        db = s.database
        add_database_to_settings(db)
        collaborates_on_fk_list = member.collaborates_on_fk_list + [service.id]
        customer_on_fk_list = member.customer_on_fk_list + [service.id]
        if partner_retailer and partner_retailer.id not in customer_on_fk_list:
            customer_on_fk_list += [partner_retailer.id]
        group_fk_list = member.group_fk_list + [new_sudo_group.id]
        Member.objects.using(db).filter(pk=member.id).update(collaborates_on_fk_list=collaborates_on_fk_list,
                                                             customer_on_fk_list=customer_on_fk_list,
                                                             group_fk_list=group_fk_list)

    member.collaborates_on_fk_list = collaborates_on_fk_list
    member.customer_on_fk_list = customer_on_fk_list
    member.group_fk_list = group_fk_list

    member.is_iao = True
    member.save(using=UMBRELLA)

    member.is_bao = True
    member.is_staff = True
    member.is_superuser = True

    app.save(using=database)
    member.save(using=database)
    logger.debug("Member %s access rights successfully set for service %s" % (member.username, pname))

    from ikwen.billing.mtnmomo.views import MTN_MOMO
    from ikwen.billing.orangemoney.views import ORANGE_MONEY
    # Copy payment means to local database
    for mean in PaymentMean.objects.using(UMBRELLA).all():
        if mean.slug == 'paypal':
            mean.action_url_name = 'shopping:paypal_set_checkout'
        if mean.slug == MTN_MOMO:
            mean.is_main = True
            mean.is_active = True
        elif mean.slug == ORANGE_MONEY:
            mean.is_main = False
            mean.is_active = True
        else:
            mean.is_main = False
            mean.is_active = False
        mean.save(using=database)
        logger.debug("PaymentMean %s created in database: %s" % (mean.slug, database))

    # Copy themes to local database
    for template in Template.objects.using(UMBRELLA).all():
        template.save(using=database)
    for th in Theme.objects.using(UMBRELLA).all():
        th.save(using=database)
    logger.debug("Template and theme successfully bound for service: %s" % pname)

    FlatPage.objects.using(database).create(url=FlatPage.AGREEMENT, title=FlatPage.AGREEMENT)
    FlatPage.objects.using(database).create(url=FlatPage.LEGAL_MENTIONS, title=FlatPage.LEGAL_MENTIONS)

    # Add member to SUDO Group
    obj_list, created = UserPermissionList.objects.using(database).get_or_create(user=member)
    obj_list.group_fk_list.append(new_sudo_group.id)
    obj_list.save(using=database)
    logger.debug("Member %s successfully added to sudo group for service: %s" % (member.username, pname))

    # Create wallets
    wallet = OperatorWallet.objects.using('wallets').create(nonrel_id=service.id, provider=MTN_MOMO)
    OperatorWallet.objects.using('wallets').create(nonrel_id=service.id, provider=ORANGE_MONEY)
    mail_signature = "%s<br>" \
                     "<a href='%s'>%s</a>" % (project_name, 'http://' + domain, domain)
    config = OperatorProfile(service=service, rel_id=wallet.id, media_url=media_url,
                             ikwen_share_fixed=billing_plan.tx_share_fixed, ikwen_share_rate=billing_plan.tx_share_rate,
                             can_manage_delivery_options=can_manage_delivery_options, business_type=business_type,
                             is_pro_version=is_pro_version, theme=theme, currency_code='XAF', currency_symbol='XAF',
                             signature=mail_signature, max_products=billing_plan.max_objects, decimal_precision=0,
                             company_name=project_name, contact_email=member.email, contact_phone=member.phone,
                             business_category=business_category, bundle=bundle, sms_api_script_url=SMS_API_URL)
    config.save(using=UMBRELLA)
    base_config = config.get_base_config()
    base_config.save(using=UMBRELLA)
    if partner_retailer:
        partner_retailer.save(using=database)

    if bundle:  # Tsunami bundle
        token = ''.join([random.SystemRandom().choice(string.digits) for i in range(6)])
        expiry = now + timedelta(days=bundle.support_bundle.duration)
        SupportCode.objects.using(UMBRELLA).create(service=service, type=bundle.support_bundle.type,
                                                   token=token, expiry=expiry)
        Balance.objects.using('wallets').create(service_id=service.id)

    service.save(using=database)
    if business_type == OperatorProfile.LOGISTICS:
        config.auth_code = auth_code

    theme.save(using=database)  # Causes theme to be routed to the newly created database
    if business_category:
        business_category.save(using=database)
    config.save(using=database)

    InvoicingConfig.objects.using(database).create()
    logger.debug("Configuration successfully added for service: %s" % pname)

    # Copy samples to local database
    for product in Product.objects.using(database).all():
        product.provider = service
        product.save(using=database)
    logger.debug("Sample products successfully copied to database %s" % database)

    # Create delivery options: Pick-up in store and Free home delivery
    DeliveryOption.objects.using(database).create(company=service, type=DeliveryOption.PICK_UP_IN_STORE,
                                                  name=_("Pick up in store"), slug='pick-up-in-store',
                                                  short_description=_("2H after order"), cost=0, max_delay=2)
    DeliveryOption.objects.using(database).create(company=service, type=DeliveryOption.HOME_DELIVERY,
                                                  name=_("Home delivery"), slug='home-delivery',
                                                  short_description=_("Max. 72H after order"), cost=500, max_delay=72)

    # Apache Server cloud_setup
    go_apache_tpl = get_template('foulassi/cloud_setup/apache.conf.local.html')
    apache_context = Context({'is_naked_domain': is_naked_domain, 'domain': domain, 'ikwen_name': ikwen_name})
    if is_naked_domain:
        apache_tpl = get_template('foulassi/cloud_setup/apache.conf.html')
        fh = open(website_home_folder + '/apache.conf', 'w')
        fh.write(apache_tpl.render(apache_context))
        fh.close()
    fh = open(website_home_folder + '/go_apache.conf', 'w')
    fh.write(go_apache_tpl.render(apache_context))
    fh.close()

    vhost = '/etc/apache2/sites-enabled/go_ikwen/' + pname + '.conf'
    subprocess.call(['sudo', 'ln', '-sf', website_home_folder + '/go_apache.conf', vhost])
    if is_naked_domain:
        vhost = '/etc/apache2/sites-enabled/' + domain + '.conf'
        subprocess.call(['sudo', 'ln', '-sf', website_home_folder + '/apache.conf', vhost])
    logger.debug("Apache Virtual Host '%s' successfully created" % vhost)

    # Send notification and Invoice to customer
    number = get_next_invoice_number()
    now = datetime.now()
    invoice_total = 0
    for entry in invoice_entries:
        invoice_total += entry.item.amount * entry.quantity
    invoice = Invoice(subscription=service, amount=invoice_total, number=number, due_date=expiry, last_reminder=now,
                      reminders_sent=1, is_one_off=True, entries=invoice_entries,
                      months_count=billing_plan.setup_months_count)
    invoice.save(using=UMBRELLA)
    vendor = get_service_instance()

    if member != vendor.member:
        add_event(vendor, SERVICE_DEPLOYED, member=member, object_id=invoice.id)
    if partner_retailer:
        partner_profile = PartnerProfile.objects.using(UMBRELLA).get(service=partner_retailer)
        try:
            Member.objects.get(pk=member.id)
        except Member.DoesNotExist:
            member.is_iao = False
            member.is_bao = False
            member.is_staff = False
            member.is_superuser = False
            member.save(using='default')
        service.save(using='default')
        config.save(using='default')
        sender = '%s <no-reply@%s>' % (partner_profile.company_name, partner_retailer.domain)
        sudo_group = Group.objects.get(name=SUDO)
        ikwen_sudo_gp = Group.objects.using(UMBRELLA).get(name=SUDO)
        add_event(vendor, SERVICE_DEPLOYED, group_id=ikwen_sudo_gp.id, object_id=invoice.id)
    else:
        sender = 'ikwen Tsunami <no-reply@ikwen.com>'
        sudo_group = Group.objects.using(UMBRELLA).get(name=SUDO)
    add_event(vendor, SERVICE_DEPLOYED, group_id=sudo_group.id, object_id=invoice.id)
    invoice_url = 'http://www.ikwen.com' + reverse('billing:invoice_detail', args=(invoice.id,))
    subject = _("Your website %s was created" % project_name)
    html_content = get_mail_content(subject, template_name='core/mails/service_deployed.html',
                                    extra_context={'service_activated': service, 'invoice': invoice,
                                                   'member': member, 'invoice_url': invoice_url})
    msg = EmailMessage(subject, html_content, sender, [member.email])
    bcc = ['contact@ikwen.com']
    if vendor.config.contact_email:
        bcc.append(vendor.config.contact_email)
    msg.bcc = list(set(bcc))
    msg.content_subtype = "html"
    Thread(target=lambda m: m.send(), args=(msg, )).start()
    logger.debug("Notice email submitted to %s" % member.email)
    Thread(target=reload_server).start()
    logger.debug("Apache Scheduled to reload in 5s")
    return service
