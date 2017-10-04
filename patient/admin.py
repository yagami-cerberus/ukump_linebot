
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


class WeeklyCheckboxInput(forms.CheckboxInput):
    template_name = "widgets/weekly_checkbox.html"

    def __init__(self, attrs=None, weekly_label=None):
        super(WeeklyCheckboxInput, self).__init__(attrs)
        self.weekly_label = weekly_label

    def get_context(self, name, value, attrs):
        context = super(WeeklyCheckboxInput, self).get_context(name, value, attrs)
        context['widget']['weekly_label'] = self.weekly_label
        return context


class WeeklyWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        widgets = (
            WeeklyCheckboxInput(attrs=attrs, weekly_label="日"),
            WeeklyCheckboxInput(attrs=attrs, weekly_label="一"),
            WeeklyCheckboxInput(attrs=attrs, weekly_label="二"),
            WeeklyCheckboxInput(attrs=attrs, weekly_label="三"),
            WeeklyCheckboxInput(attrs=attrs, weekly_label="四"),
            WeeklyCheckboxInput(attrs=attrs, weekly_label="五"),
            WeeklyCheckboxInput(attrs=attrs, weekly_label="六")
        )
        super(WeeklyWidget, self).__init__(widgets, attrs)

    def value_from_datadict(self, data, files, name):
        val = 0
        for i, checked in enumerate(super(WeeklyWidget, self).value_from_datadict(data, files, name)):
            if checked:
                val += (1 << i)
        if val:
            return val
        else:
            return None

    def decompress(self, value):
        if value:
            return tuple(bool(value & (1 << i)) for i in range(7))
        else:
            return tuple(False for i in range(7))


class CourseScheduleForm(forms.ModelForm):
    class Meta:
        model = models.CourseSchedule
        exclude = ()
        widgets = {
            'weekly_mask': WeeklyWidget
        }


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
    form = CourseScheduleForm


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
