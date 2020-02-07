from django.conf.urls import patterns, include, url

from django.contrib import admin
from ikwen.accesscontrol.views import SignIn

admin.autodiscover()

urlpatterns = patterns(
    '',
    url(r'^$', SignIn.as_view(), name='home'),
    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r'^billing/', include('ikwen.billing.urls', namespace='billing')),
    url(r'^school/', include('ikwen_foulassi.school.urls', namespace='school')),
    url(r'^', include('ikwen_foulassi.foulassi.urls', namespace='foulassi')),
    url(r'^', include('ikwen.core.urls', namespace='ikwen')),
)
