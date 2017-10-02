
from django.contrib import admin
from django import forms

from customer import models


class CustomerForm(forms.ModelForm):
    class Meta:
        model = models.Profile
        exclude = ()
        widgets = {
            'name': forms.TextInput,
            'phone': forms.TextInput
        }


class LineBotIntegrationForm(forms.ModelForm):
    class Meta:
        model = models.LineBotIntegration
        exclude = ()
        widgets = {
            'lineid': forms.TextInput(attrs={"size": "36"})
        }


class LineBotIntegrationInline(admin.TabularInline):
    extra = 1
    model = models.LineBotIntegration
    form = LineBotIntegrationForm


@admin.register(models.Profile)
class CustomerAdmin(admin.ModelAdmin):
    form = CustomerForm
    inlines = (LineBotIntegrationInline, )
    list_display = ("id", "name", "created_at")
