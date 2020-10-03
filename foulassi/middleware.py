
from django.conf import settings
from django.core.urlresolvers import reverse
from django.http.response import HttpResponseRedirect

from ikwen.accesscontrol.backends import UMBRELLA
from ikwen.core.utils import get_service_instance
from ikwen_foulassi.foulassi.models import SchoolConfig


class WebsiteServiceStatusCheckMiddleWare(object):
    """
    This middleware redirects URLs having these following namespaces: webnode, about, and terms & conditions to
    login page and check if the user paid the website service or not. Then, he is routed to buy website page or on home
     page.
    :param object:
    :return:
    """
    def process_view(self, request, view_func, view_args, view_kwargs):
        if getattr(settings, 'IS_IKWEN', False):
            return
        rm = request.resolver_match
        service = get_service_instance(using=UMBRELLA)
        if service.config.website_is_active:
            return
        name_list = ['home', 'about', 'terms_and_conditions']
        if rm.namespace == 'webnode' or (not rm.namespace and rm.url_name in name_list):
            return HttpResponseRedirect(reverse('ikwen:sign_in'))



