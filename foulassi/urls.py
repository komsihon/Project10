
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import login_required, permission_required

from ikwen_foulassi.foulassi.views import KidList, KidDetail, ShowJustificatory, AccessDenied, \
    Home, HomeSaaS, SearchSchool, EventList, DeployCloud, SuccessfulDeployment, AdminHome, ChangeHomework, \
    DownloadApp, TermsAndConditions
from ikwen_foulassi.foulassi.cash_in import confirm_invoice_payment, confirm_my_kids_payment

urlpatterns = patterns(
    '',
    url(r'^$', Home.as_view(), name='home'),
    url(r'^for-schools$', HomeSaaS.as_view(), name='home_saas'),
    url(r'^events/$', permission_required('foulassi.ik_view_event')(EventList.as_view()), name='event_list'),
    url(r'^deploy$', login_required(DeployCloud.as_view()), name='deploy_cloud'),
    url(r'^terms-and-conditions/$', login_required(TermsAndConditions.as_view()), name='terms_and_conditions'),
    url(r'^successfulDeployment/(?P<ikwen_name>[-\w]+)$', login_required(SuccessfulDeployment.as_view()), name='successful_deployment'),
    url(r'^home/$', AdminHome.as_view(), name='admin_home'),

    url(r'^search/$', login_required(SearchSchool.as_view()), name='search_school'),
    url(r'^downloadApp/$', DownloadApp.as_view(), name='download_app'),
    url(r'^kids/$', login_required(KidList.as_view()), name='kid_list'),
    url(r'^accessDenied/$', AccessDenied.as_view(), name='access_denied'),
    url(r'^confirm_invoice_payment/(?P<tx_id>[-\w]+)/(?P<signature>[-\w]+)$', confirm_invoice_payment, name='confirm_invoice_payment'),
    url(r'^confirm_my_kids_payment/(?P<tx_id>[-\w]+)/(?P<signature>[-\w]+)$', confirm_my_kids_payment, name='confirm_my_kids_payment'),

    url(r'^(?P<ikwen_name>[-\w]+)/kid/(?P<student_id>[-\w]+)$', login_required(KidDetail.as_view()), name='kid_detail'),
    url(r'^(?P<ikwen_name>[-\w]+)/kid/(?P<student_id>[-\w]+)/(?P<assignment_id>[-\w]+)$', login_required(ChangeHomework.as_view()), name='change_homework'),
    url(r'^(?P<ikwen_name>[-\w]+)/kid/(?P<student_id>[-\w]+)/(?P<assignment_id>[-\w]+)/(?P<homework_id>[-\w]+)$', login_required(ChangeHomework.as_view()), name='change_homework'),
    url(r'^(?P<ikwen_name>[-\w]+)/justificatory/(?P<object_id>[-\w]+)$', login_required(ShowJustificatory.as_view()),
        name='show_justificatory'),
)
