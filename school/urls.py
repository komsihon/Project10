
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import permission_required
from ikwen_foulassi.school.views import LevelList, ChangeLevel, SubjectList, ChangeSubject, ClassroomList, \
    AddClassroom, ClassroomDetail, ChangeStudent, ChangeSession

urlpatterns = patterns(
    '',
    url(r'^levels/$', permission_required('school.ik_manage_school')(LevelList.as_view()), name='level_list'),
    url(r'^level/$', permission_required('school.ik_manage_school')(ChangeLevel.as_view()), name='change_level'),
    url(r'^level/(?P<object_id>[-\w]+)/$', permission_required('school.ik_manage_school')(ChangeLevel.as_view()), name='change_level'),

    url(r'^subjects/$', permission_required('school.ik_manage_school')(SubjectList.as_view()), name='subject_list'),
    url(r'^subject/$', permission_required('school.ik_manage_school')(ChangeSubject.as_view()), name='change_subject'),
    url(r'^subject/(?P<object_id>[-\w]+)/$', permission_required('school.ik_manage_school')(ChangeSubject.as_view()),
        name='change_subject'),

    url(r'^sessions/$', permission_required('school.ik_manage_school')(LevelList.as_view()), name='session_list'),
    url(r'^session/$', permission_required('school.ik_manage_school')(ChangeSession.as_view()), name='change_session'),
    url(r'^session/(?P<object_id>[-\w]+)/$', permission_required('school.ik_manage_school')(ChangeSession.as_view()),
        name='change_session'),

    url(r'^classrooms/$', permission_required('school.ik_manage_school')(ClassroomList.as_view()), name='classroom_list'),
    url(r'^classroom/$', permission_required('school.ik_manage_school')(AddClassroom.as_view()), name='add_classroom'),
    url(r'^classroom/(?P<object_id>[-\w]+)/$', permission_required('school.ik_manage_school')(ClassroomDetail.as_view()),
        name='classroom_detail'),

    url(r'^student/$', permission_required('school.ik_manage_student')(ChangeStudent.as_view()), name='change_student'),
    url(r'^student/(?P<object_id>[-\w]+)/$', permission_required('school.ik_manage_student')(ChangeStudent.as_view()),
        name='change_student'),
)
