from django.contrib import admin


class StudentAdmin(admin.ModelAdmin):
    fields = ('first_name', 'last_name', 'gender', 'dob', 'classroom', 'is_repeating', 'year_joined',)
