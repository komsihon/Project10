from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.billing.models import Invoice
from ikwen.core.utils import get_service_instance
from ikwen_foulassi.foulassi.models import Event, SchoolConfig
from ikwen_foulassi.school.models import Session

from echo.models import Balance


def echo_balance(request):
    service = get_service_instance()
    balance, update = Balance.objects.using('wallets').get_or_create(service_id=service.id)
    return {
        'balance': balance
    }


def event_count(request):
    count = Event.objects.filter(is_processed=False).count()
    if count >= 10:
        count = "9+"
    return {
        'event_count': count
    }


def current_session(request):
    return {
        'current_session': Session.get_current()
    }


def website_is_active(request):
    service = get_service_instance()
    try:
        school = SchoolConfig.objects.get(service=service)
    except:
        return {
            'has_subscribed_website_service': False,
            'website_is_active': False
        }
    return {
        'has_subscribed_website_service': school.has_subscribed_website_service,
        'website_is_active': school.website_is_active
    }