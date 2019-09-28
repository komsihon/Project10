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
from ikwen.core.models import Service, OperatorWallet, SERVICE_DEPLOYED, Application
from ikwen.core.tools import generate_django_secret_key, generate_random_key, reload_server
from ikwen.core.utils import add_database_to_settings, add_event, get_mail_content, \
    get_service_instance
from ikwen.flatpages.models import FlatPage
from ikwen.partnership.models import PartnerProfile
from ikwen.theming.models import Template, Theme
from ikwen_foulassi.foulassi.models import SchoolConfig

from echo.models import Balance

import logging
logger = logging.getLogger('ikwen')


if getattr(settings, 'LOCAL_DEV', False):
    CLOUD_HOME = '/home/komsihon/PycharmProjects/CloudTest/'
else:
    CLOUD_HOME = '/home/ikwen/Cloud/'

CLOUD_FOLDER = CLOUD_HOME + 'Foulassi/'
SMS_API_URL = 'http://websms.mobinawa.com/http_api?action=sendsms&username=675187705&password=depotguinness&from=$label&to=$recipient&msg=$text'


class DeploymentForm(forms.Form):
    """
    Deployment form of a platform
    """
    partner_id = forms.CharField(max_length=24, required=False)  # Service ID of the partner retail platform
    customer_id = forms.CharField(max_length=24)
    project_name = forms.CharField(max_length=30)
    billing_plan_id = forms.CharField(max_length=24)
    bundle_id = forms.CharField(max_length=24, required=False)
    setup_cost = forms.FloatField(required=False)
    monthly_cost = forms.FloatField(required=False)


def deploy(member, project_name, billing_plan, theme, monthly_cost, invoice_entries, partner_retailer=None):
    app = Application.objects.using(UMBRELLA).get(slug='foulassi')
    project_name_slug = slugify(project_name)  # Eg: slugify('Great School') = 'great-school'
    ikwen_name = project_name_slug.replace('-', '')  # Eg: great-school --> 'greatschool'
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
    admin_url = url + '/ikwen' + reverse('ikwen:staff_router')
    now = datetime.now()
    expiry = now + timedelta(days=60)

    # Create a copy of template application in the Cloud folder
    app_folder = CLOUD_HOME + '000Tpl/AppSkeleton'
    website_home_folder = CLOUD_FOLDER + ikwen_name
    media_root = CLUSTER_MEDIA_ROOT + ikwen_name + '/'
    media_url = CLUSTER_MEDIA_URL + ikwen_name + '/'
    images_folder = CLOUD_FOLDER + '000Tpl/images/000Default'
    if theme:
        theme_images_folder = CLOUD_FOLDER + '000Tpl/images/%s/%s' % (theme.template.slug, theme.slug)
        if os.path.exists(theme_images_folder):
            images_folder = theme_images_folder
    if os.path.exists(images_folder):
        if os.path.exists(media_root):
            shutil.rmtree(media_root)
        shutil.copytree(images_folder, media_root)
        logger.debug("Media folder '%s' successfully created from '%s'" % (media_root, images_folder))
    elif not os.path.exists(media_root):
        os.makedirs(media_root)
        logger.debug("Media folder '%s' successfully created empty" % media_root)
    icons_folder = media_root + 'icons'
    if not os.path.exists(icons_folder):
        os.makedirs(icons_folder)
    if os.path.exists(website_home_folder):
        shutil.rmtree(website_home_folder)
    shutil.copytree(app_folder, website_home_folder)
    logger.debug("Service folder '%s' successfully created" % website_home_folder)

    settings_template = 'foulassi/cloud_setup/settings.html'

    service = Service(member=member, app=app, project_name=project_name, project_name_slug=ikwen_name, domain=domain,
                      database=database, url=url, domain_type=domain_type, expiry=expiry, admin_url=admin_url,
                      billing_plan=billing_plan, billing_cycle=Service.YEARLY, monthly_cost=monthly_cost,
                      version=Service.TRIAL, api_signature=api_signature, home_folder=website_home_folder,
                      settings_template=settings_template, retailer=partner_retailer)
    service.save(using=UMBRELLA)
    logger.debug("Service %s successfully created" % pname)

    # Re-create settings.py file as well as apache.conf file for the newly created project
    secret_key = generate_django_secret_key()
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
    db_folder = CLOUD_FOLDER + '000Tpl/DB/000Default'
    if theme:
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
    # Copy payment means to local database
    for mean in PaymentMean.objects.using(UMBRELLA).all():
        if mean.slug == MTN_MOMO:
            mean.is_main = True
            mean.is_active = True
        else:
            mean.is_main = False
            mean.is_active = True
        mean.save(using=database)
        logger.debug("PaymentMean %s created in database: %s" % (mean.slug, database))

    # Copy themes to local database
    webnode = Application.objects.using(UMBRELLA).get(slug='webnode')
    template_list = list(Template.objects.using(UMBRELLA).filter(app=webnode))
    for template in template_list:
        template.save(using=database)
    for th in Theme.objects.using(UMBRELLA).filter(template__in=template_list):
        th.save(using=database)
    logger.debug("Templates and themes successfully saved for service: %s" % pname)

    FlatPage.objects.using(database).get_or_create(url=FlatPage.AGREEMENT, title=FlatPage.AGREEMENT)
    FlatPage.objects.using(database).get_or_create(url=FlatPage.LEGAL_MENTIONS, title=FlatPage.LEGAL_MENTIONS)

    # Add member to SUDO Group
    obj_list, created = UserPermissionList.objects.using(database).get_or_create(user=member)
    obj_list.group_fk_list.append(new_sudo_group.id)
    obj_list.save(using=database)
    logger.debug("Member %s successfully added to sudo group for service: %s" % (member.username, pname))

    mail_signature = "%s<br>" \
                     "<a href='%s'>%s</a>" % (project_name, 'http://' + domain, domain)
    config = SchoolConfig(service=service, ikwen_share_rate=billing_plan.tx_share_rate,
                          theme=theme, currency_code='XAF', currency_symbol='XAF', decimal_precision=0,
                          signature=mail_signature, company_name=project_name, contact_email=member.email,
                          contact_phone=member.phone, sms_api_script_url=SMS_API_URL)
    config.save(using=UMBRELLA)
    base_config = config.get_base_config()
    base_config.save(using=UMBRELLA)

    service.save(using=database)
    theme.save(using=database)  # Causes theme to be routed to the newly created database
    config.save(using=database)
    logger.debug("Configuration successfully added for service: %s" % pname)

    # Apache Server cloud_setup
    go_apache_tpl = get_template('foulassi/cloud_setup/apache.conf.local.html')
    apache_context = Context({'is_naked_domain': is_naked_domain, 'domain': domain, 'ikwen_name': ikwen_name})
    fh = open(website_home_folder + '/go_apache.conf', 'w')
    fh.write(go_apache_tpl.render(apache_context))
    fh.close()

    vhost = '/etc/apache2/sites-enabled/go_ikwen/' + pname + '.conf'
    subprocess.call(['sudo', 'ln', '-sf', website_home_folder + '/go_apache.conf', vhost])
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
        sender = 'ikwen Foulassi <no-reply@ikwen.com>'
        sudo_group = Group.objects.using(UMBRELLA).get(name=SUDO)
    add_event(vendor, SERVICE_DEPLOYED, group_id=sudo_group.id, object_id=invoice.id)
    invoice_url = 'http://www.ikwen.com' + reverse('billing:invoice_detail', args=(invoice.id,))
    subject = _("Your platform %s was created" % project_name)
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
