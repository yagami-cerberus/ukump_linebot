from django.contrib import admin
from django import forms

from care import models


class QuestionForm(forms.ModelForm):
    class Meta:
        model = models.Course
        exclude = ()
        widgets = {
            'question': forms.TextInput
        }


class CourseForm(forms.ModelForm):
    class Meta:
        model = models.Course
        exclude = ()
        widgets = {
            'name': forms.TextInput
        }


class CourseDetailForm(forms.ModelForm):
    class Meta:
        model = models.CourseDetail
        exclude = ()
        widgets = {
            'name': forms.TextInput
        }


@admin.register(models.Question)
class QuestionAdmin(admin.ModelAdmin):
    form = QuestionForm


class CourseDetailInline(admin.TabularInline):
    extra = 1
    model = models.CourseDetail
    form = CourseDetailForm


class CourseQuestionInline(admin.TabularInline):
    extra = 1
    model = models.CourseQuestion


@admin.register(models.Course)
class CourseAdmin(admin.ModelAdmin):
    inlines = (CourseDetailInline, CourseQuestionInline, )
    list_display = ("id", "name")
    form = CourseForm
