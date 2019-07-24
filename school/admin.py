from django.contrib import admin


class LevelAdmin(admin.ModelAdmin):
    fields = ('name', 'tuition_fees', )


class ClassroomAdmin(admin.ModelAdmin):
    fields = ('level', 'name', 'tuition_fees', 'professor')


class SubjectAdmin(admin.ModelAdmin):
    fields = ('name', )


class SessionAdmin(admin.ModelAdmin):
    fields = ('session_group', 'name', 'starts_on', 'ends_on')


class SessionGroupAdmin(admin.ModelAdmin):
    fields = ('name', 'starts_on', 'ends_on', )


class DisciplineItemAdmin(admin.ModelAdmin):
    fields = ('name', 'unit', )


class JustificatoryAdmin(admin.ModelAdmin):
    fields = ('details', )
