from django.conf import settings
from django.contrib import admin
from django.utils.translation import gettext as _

from import_export import resources, fields
from ikwen.core.utils import get_service_instance

from ikwen_foulassi.foulassi.models import Student


class StudentResource(resources.ModelResource):
    last_name = fields.Field(column_name=_('Last name'))
    first_name = fields.Field(column_name=_('First name'))
    gender = fields.Field(column_name=_('Gender'))
    dob = fields.Field(column_name=_('Date of birth'))
    classroom = fields.Field(column_name=_('Classroom'))
    is_repeating = fields.Field(column_name=_('Repeats'))
    year_joined = fields.Field(column_name=_('Year joined'))
    school_year = fields.Field(column_name=_('School year'))

    class Meta:
        model = Student
        fields = ('last_name', 'first_name', 'gender', 'dob', 'classroom', 'is_repeating', 'year_joined', 'school_year')
        export_order = ('last_name', 'first_name', 'gender', 'dob',
                        'classroom', 'is_repeating', 'year_joined', 'school_year')

    def dehydrate_last_name(self, obj):
        return obj.last_name

    def dehydrate_first_name(self, obj):
        return obj.first_name

    def dehydrate_gender(self, obj):
        return obj.gender

    def dehydrate_dob(self, obj):
        if obj.dob:
            return obj.dob.strftime('%Y-%m-%d')
        return 'N/A'

    def dehydrate_classroom(self, obj):
        return str(obj.classroom)

    def dehydrate_is_repeating(self, obj):
        return _("Yes") if obj.is_repeating else _("No")

    def dehydrate_year_joined(self, obj):
        return obj.year_joined

    def dehydrate_school_year(self, obj):
        return obj.school_year


class StudentAdmin(admin.ModelAdmin):
    fields = ('classroom', 'registration_number', 'last_name', 'first_name', 'gender', 'dob', 'is_repeating', 'year_joined', )


if getattr(settings, 'IS_IKWEN', False):
    _fieldsets = [
        (_('School'), {'fields': ('company_name', 'short_description', 'slogan', 'latitude', 'longitude',
                                  'description', 'is_pro_version')}),
        (_('SMS'), {'fields': ('sms_api_script_url', 'sms_api_username', 'sms_api_password', )}),
        (_('Mailing'), {'fields': ('welcome_message', 'signature',)})
    ]
else:
    service = get_service_instance()
    config = service.config

    _fieldsets = [
        (_('School'), {'fields': ('company_name', 'short_description', 'slogan', 'description', 'back_to_school_date')}),
        (_('Address & Contact'), {'fields': ('contact_email', 'contact_phone', 'address', 'country', 'city',
                                             'latitude', 'longitude',)}),
        (_('Social'), {'fields': ('facebook_link', 'twitter_link', 'google_plus_link', 'youtube_link', 'instagram_link',
                                  'tumblr_link', 'linkedin_link', )}),
        (_('Mailing'), {'fields': ('welcome_message', 'signature', )}),
        (_('External scripts'), {'fields': ('scripts', )}),
    ]


class SchoolConfigAdmin(admin.ModelAdmin):
    list_display = ('service', 'company_name')
    fieldsets = _fieldsets
    # readonly_fields = ('api_signature', )
    list_filter = ('company_name', 'contact_email', )
    save_on_top = True

    def delete_model(self, request, obj):
        self.message_user(request, "You are not allowed to delete Configuration of the platform")
