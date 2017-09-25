from django.contrib import admin
from django import forms
from employee import models


class PatientForm(forms.ModelForm):
    class Meta:
        model = models.Profile
        exclude = ()
        widgets = {
            'name': forms.TextInput
        }


class LineBotIntegrationForm(forms.ModelForm):
    class Meta:
        model = models.LineBotIntegration
        exclude = ()
        widgets = {
            'lineid': forms.TextInput
        }


class LineBotIntegrationInline(admin.TabularInline):
    extra = 1
    model = models.LineBotIntegration
    form = LineBotIntegrationForm


@admin.register(models.Profile)
class EmployeeAdmin(admin.ModelAdmin):
    form = PatientForm
    inlines = (LineBotIntegrationInline, )
    list_display = ("id", "name", "created_at")
