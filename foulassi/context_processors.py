from ikwen.core.utils import get_service_instance
from ikwen_foulassi.foulassi.models import Event
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
