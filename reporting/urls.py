
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import permission_required
from ikwen_foulassi.reporting.views import Dashboard, DisciplineDetail, generate_report_cards, ReportCardDownloadList

urlpatterns = patterns(
    '',
    url(r'^dashboard/$', permission_required('reporting.ik_view_dashboard')(Dashboard.as_view()), name='dashboard'),
    url(r'^disciplineDetail/$', permission_required('reporting.ik_view_dashboard')(DisciplineDetail.as_view()), name='discipline_detail'),
    url(r'^downloadList/(?P<session_id>[-\w]+)/$', permission_required('reporting.ik_manage_reporting')(ReportCardDownloadList.as_view()), name='report_card_download_list'),
    url(r'^generate_report_cards$', generate_report_cards, name='generate_report_cards'),
)
