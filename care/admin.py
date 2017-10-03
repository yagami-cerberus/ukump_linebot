from django.contrib import admin

from care import models


class CourseItemInline(admin.TabularInline):
    extra = 1
    model = models.CourseItem


@admin.register(models.Course)
class CourseAdmin(admin.ModelAdmin):
    inlines = (CourseItemInline, )
    list_display = ("id", "name")
