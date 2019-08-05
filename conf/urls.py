from django.conf.urls import patterns, include, url

from django.contrib.auth.decorators import permission_required
from django.contrib import admin
from ikwen_foulassi.foulassi.views import EventList
from ikwen_webnode.webnode.views import Home, AdminHome, FlatPageView

admin.autodiscover()

urlpatterns = patterns(
    '',
    url(r'^$', Home.as_view(), name='home'),
    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r'^billing/', include('ikwen.billing.urls', namespace='billing')),
    url(r'^cashout/', include('ikwen.cashout.urls', namespace='cashout')),
    url(r'^theming/', include('ikwen.theming.urls', namespace='theming')),
    url(r'^revival/', include('ikwen.revival.urls', namespace='revival')),
    url(r'^ikwen/', include('ikwen.core.urls', namespace='ikwen')),

    url(r'^page/(?P<url>[-\w]+)/$', FlatPageView.as_view(), name='flatpage'),
    url(r'^blog/', include('ikwen_webnode.blog.urls', namespace='blog')),
    url(r'^web/', include('ikwen_webnode.web.urls', namespace='web')),
    url(r'^items/', include('ikwen_webnode.items.urls', namespace='items')),
    url(r'^echo/', include('echo.urls', namespace='echo')),

    url(r'^reporting/', include('ikwen_foulassi.reporting.urls', namespace='reporting')),
    url(r'^school/', include('ikwen_foulassi.school.urls', namespace='school')),
    url(r'^foulassi/', include('ikwen_foulassi.foulassi.urls', namespace='foulassi')),

    url(r'^', include('ikwen_webnode.webnode.urls', namespace='webnode')),
)
