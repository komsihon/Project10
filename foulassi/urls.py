
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import login_required, permission_required

from ikwen_foulassi.foulassi.views import KidList, KidDetail, ShowJustificatory, AccessDenied, confirm_invoice_payment, \
    Home, SearchSchool, EventList

urlpatterns = patterns(
    '',
    url(r'^$', Home.as_view(), name='home'),
    url(r'^search/$', login_required(SearchSchool.as_view()), name='search_school'),
    url(r'^kids/$', login_required(KidList.as_view()), name='kid_list'),
    url(r'^(?P<ikwen_name>[-\w]+)/kid/(?P<student_id>[-\w]+)$', login_required(KidDetail.as_view()), name='kid_detail'),
    url(r'^(?P<ikwen_name>[-\w]+)/justificatory/(?P<object_id>[-\w]+)$', login_required(ShowJustificatory.as_view()),
        name='show_justificatory'),
    url(r'^accessDenied/$', AccessDenied.as_view(), name='access_denied'),
    url(r'^confirm_invoice_payment/(?P<tx_id>[-\w]+)$', confirm_invoice_payment, name='confirm_invoice_payment'),
    url(r'^events/$', permission_required('foulassi.ik_view_event')(EventList.as_view()), name='event_list'),
)
