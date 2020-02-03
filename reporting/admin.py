from django.contrib import admin


class ReportCardHeaderAdmin (admin.ModelAdmin):
    fields = ('country_name', 'country_moto', 'head_organization', 'lang')
