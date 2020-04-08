from django.contrib import admin
from django.utils.translation import gettext_lazy as _


class LevelAdmin(admin.ModelAdmin):
    fields = ('name', 'registration_fees', 'first_instalment', 'second_instalment', 'third_instalment')
    fieldsets = (
        (None, {'fields': ('name', )}),
        (_('Tuition fees'), {'fields': ('registration_fees', 'first_instalment', 'second_instalment', 'third_instalment')}),
    )


class ClassroomAdmin(admin.ModelAdmin):
    fields = ('level', 'name', 'professor',
              'registration_fees', 'first_instalment', 'second_instalment', 'third_instalment')
    fieldsets = (
        (None, {'fields': ('level', 'name', 'professor', )}),
        (_('Tuition fees'), {'fields': ('registration_fees', 'first_instalment', 'second_instalment', 'third_instalment')}),
    )


class AssignmentAdmin(admin.ModelAdmin):
    fields = ('subject', 'classroom', 'title', 'detail', 'attachment', 'deadline')


class HomeworkAdmin(admin.ModelAdmin):
    fields = ('assignment', 'student', 'attachment', )


class SubjectAdmin(admin.ModelAdmin):
    fields = ('name', )


class SessionAdmin(admin.ModelAdmin):
    fields = ('session_group', 'name', 'starts_on', 'ends_on')


class SessionGroupAdmin(admin.ModelAdmin):
    fields = ('name', 'starts_on', 'ends_on', )


class DisciplineItemAdmin(admin.ModelAdmin):
    fields = ('name', 'unit', 'has_count')


class JustificatoryAdmin(admin.ModelAdmin):
    fields = ('details', )

