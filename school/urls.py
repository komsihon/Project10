
from django.conf.urls import patterns, url
from django.contrib.auth.decorators import permission_required, user_passes_test
from ikwen_foulassi.school.student.views import ChangeStudent, StudentDetail, ChangeJustificatory, ViewHomework
from ikwen_foulassi.school.classroom.views import ClassroomList, ChangeClassroom, ClassroomDetail, upload_student_file, \
    AssignmentList, ChangeAssignment
from ikwen_foulassi.school.views import LevelList, ChangeLevel, SubjectList, ChangeSubject, ChangeSession, \
    SessionList, DisciplineItemList, ChangeDisciplineItem, TeacherList, TeacherDetail, SessionGroupList, \
    ChangeSessionGroup, close_session
from ikwen_foulassi.foulassi.utils import access_classroom

urlpatterns = patterns(
    '',
    url(r'^levels/$', permission_required('school.ik_manage_school')(LevelList.as_view()), name='level_list'),
    url(r'^level/$', permission_required('school.ik_manage_school')(ChangeLevel.as_view()), name='change_level'),
    url(r'^level/(?P<object_id>[-\w]+)/$', permission_required('school.ik_manage_school')(ChangeLevel.as_view()), name='change_level'),

    url(r'^subjects/$', permission_required('school.ik_manage_school')(SubjectList.as_view()), name='subject_list'),
    url(r'^subject/$', permission_required('school.ik_manage_school')(ChangeSubject.as_view()), name='change_subject'),
    url(r'^subject/(?P<object_id>[-\w]+)/$', permission_required('school.ik_manage_school')(ChangeSubject.as_view()),
        name='change_subject'),

    url(r'^sessions/$', permission_required('school.ik_manage_school')(SessionList.as_view()), name='session_list'),
    url(r'^session/$', permission_required('school.ik_manage_school')(ChangeSession.as_view()), name='change_session'),
    url(r'^session/(?P<object_id>[-\w]+)/$', permission_required('school.ik_manage_school')(ChangeSession.as_view()),
        name='change_session'),

    url(r'^sessionGroups/$', permission_required('school.ik_manage_school')(SessionGroupList.as_view()), name='sessiongroup_list'),
    url(r'^sessionGroup/$', permission_required('school.ik_manage_school')(ChangeSessionGroup.as_view()), name='change_sessiongroup'),
    url(r'^sessionGroup/(?P<object_id>[-\w]+)/$', permission_required('school.ik_manage_school')(ChangeSessionGroup.as_view()),
        name='change_sessiongroup'),

    url(r'^discipline/$', permission_required('school.ik_manage_school')(DisciplineItemList.as_view()), name='disciplineitem_list'),
    url(r'^disciplineItem/$', permission_required('school.ik_manage_school')(ChangeDisciplineItem.as_view()), name='change_disciplineitem'),
    url(r'^disciplineItem/(?P<object_id>[-\w]+)/$', permission_required('school.ik_manage_school')(ChangeDisciplineItem.as_view()),
        name='change_disciplineitem'),

    url(r'^classrooms/$', user_passes_test(access_classroom)(ClassroomList.as_view()), name='classroom_list'),
    url(r'^classroom/$', permission_required('school.ik_manage_school')(ChangeClassroom.as_view()), name='change_classroom'),
    url(r'^classroom/(?P<object_id>[-\w]+)/$', permission_required('school.ik_manage_school')(ChangeClassroom.as_view()),
        name='change_classroom'),
    url(r'^classroomDetail/(?P<object_id>[-\w]+)/$', user_passes_test(access_classroom)(ClassroomDetail.as_view()),
        name='classroom_detail'),

    url(r'^assignments/$', user_passes_test(access_classroom)(AssignmentList.as_view()),
        name='assignment_list'),
    url(r'^assignment/(?P<classroom_id>[-\w]+)/$', user_passes_test(access_classroom)(ChangeAssignment.as_view()),
        name='change_assignment'),
    url(r'^assignment/(?P<classroom_id>[-\w]+)/(?P<object_id>[-\w]+)/$', user_passes_test(access_classroom)(ChangeAssignment.as_view()),
        name='change_assignment'),
    url(r'^homework/(?P<object_id>[-\w]+)/$', user_passes_test(access_classroom)(ViewHomework.as_view()), name='view_homework'),


    url(r'^upload_student_file/$', permission_required('foulassi.ik_manage_student')(upload_student_file), name='upload_student_file'),
    url(r'^newStudent/(?P<classroom_id>[-\w]+)/$', permission_required('foulassi.ik_manage_student')(ChangeStudent.as_view()), name='change_student'),
    url(r'^student/(?P<object_id>[-\w]+)/$', permission_required('foulassi.ik_manage_student')(StudentDetail.as_view()),
        name='student_detail'),
    url(r'^justificatory/$', permission_required('foulassi.ik_manage_student')(ChangeJustificatory.as_view()),
        name='change_justificatory'),
    url(r'^justificatory/(?P<object_id>[-\w]+)/$', permission_required('foulassi.ik_manage_student')(ChangeJustificatory.as_view()),
        name='change_justificatory'),

    url(r'^teachers/$', permission_required('foulassi.ik_manage_teacher')(TeacherList.as_view()), name='teacher_list'),
    url(r'^teacher/(?P<object_id>[-\w]+)/$', permission_required('foulassi.ik_manage_teacher')(TeacherDetail.as_view()), name='teacher_detail'),
    url(r'^close_session$', close_session, name='close_session'),
)
