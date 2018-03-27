from django.conf.urls import patterns, include, url

from django.contrib import admin
from ikwen.core.views import DefaultHome

admin.autodiscover()

urlpatterns = patterns('',
    url(r'^$', DefaultHome.as_view(), name='home'),
    url(r'^school/', include('ikwen_foulassi.school.urls', namespace='school')),
)
