
from django.contrib import admin
from django.utils import timezone
from django import forms
from patient import models


class PatientForm(forms.ModelForm):
    class Meta:
        model = models.Profile
        exclude = ()
        widgets = {
            'name': forms.TextInput
        }


class GuardianForm(forms.ModelForm):
    class Meta:
        model = models.Guardian
        exclude = ()
        widgets = {
            'relation': forms.TextInput
        }


class ManagerForm(forms.ModelForm):
    class Meta:
        model = models.Guardian
        exclude = ()
        widgets = {
            'relation': forms.TextInput
        }


# class CourseScheduleForm(forms.ModelForm):
#     class Meta:
#         model = models.CourseSchedule
#         exclude = ()


class PatientGuardianInline(admin.TabularInline):
    extra = 1
    model = models.Guardian
    form = GuardianForm


class PatientManagerInline(admin.TabularInline):
    extra = 1
    model = models.Manager
    form = ManagerForm


class PatientCourseScheduleInline(admin.TabularInline):
    extra = 1
    model = models.CourseSchedule


@admin.register(models.Profile)
class PatientAdmin(admin.ModelAdmin):
    form = PatientForm
    inlines = (PatientGuardianInline, PatientManagerInline, PatientCourseScheduleInline)
    list_display = ("id", "name", "birthday", "created_at")


@admin.register(models.NursingSchedule)
class NursingScheduleAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "employee", "format_schedule")
    exclude = ("flow_control", )

    def format_schedule(self, record):
        return "%s - %s" % (timezone.localtime(record.schedule.lower).strftime("%Y-%m-%d %H:%M"),
                            timezone.localtime(record.schedule.upper).strftime("%Y-%m-%d %H:%M"))

    format_schedule.short_description = "schedule"
    format_schedule.admin_order_field = "schedule"
