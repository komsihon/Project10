from django.contrib import admin


class LevelAdmin(admin.ModelAdmin):
    fields = ('name', 'tuition_fees', )


class ClassroomAdmin(admin.ModelAdmin):
    fields = ('level', 'name', 'tuition_fees', )


class SubjectAdmin(admin.ModelAdmin):
    fields = ('name', )


class SessionAdmin(admin.ModelAdmin):
    fields = ('name', )
