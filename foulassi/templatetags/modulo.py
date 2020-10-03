from django.conf import settings

from django import template
from django.template.defaultfilters import stringfilter
from ikwen.core.utils import get_service_instance

register = template.Library()


@register.filter
def modulo(num, val):
    """
    Take two integers and return their modulo
    :param num:
    :param val:
    :return:
    """
    return num % val