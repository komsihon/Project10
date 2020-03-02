
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import permission_required
from ikwen_foulassi.reporting.views import Dashboard, DisciplineDetail, generate_report_cards, ReportCardDownloadList, \
    ReportCardHeaderList, ChangeReportCardHeader

urlpatterns = patterns(
    '',
    url(r'^dashboard/$', permission_required('reporting.ik_view_dashboard')(Dashboard.as_view()), name='dashboard'),
    url(r'^disciplineDetail/$', permission_required('reporting.ik_view_dashboard')(DisciplineDetail.as_view()), name='discipline_detail'),

    url(r'^reportCardHeaders/$', permission_required('reporting.ik_manage_reporting')(ReportCardHeaderList.as_view()), name='reportcardheader_list'),
    url(r'^reportCardHeader/$', permission_required('reporting.ik_manage_reporting')(ChangeReportCardHeader.as_view()), name='change_reportcardheader'),
    url(r'^reportCardHeader/(?P<object_id>[-\w]+)/$', permission_required('reporting.ik_manage_reporting')(ChangeReportCardHeader.as_view()), name='change_reportcardheader'),

    url(r'^downloadList/(?P<session_id>[-\w]+)/$', permission_required('reporting.ik_manage_reporting')(ReportCardDownloadList.as_view()), name='report_card_download_list'),
    url(r'^downloadList/(?P<session_id>[-\w]+)/(?P<classroom_id>[-\w]+)/$', permission_required('reporting.ik_manage_reporting')(ReportCardDownloadList.as_view()), name='report_card_download_list'),
    url(r'^generate_report_cards$', generate_report_cards, name='generate_report_cards'),
)
