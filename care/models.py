
from django.contrib.postgres.fields import ArrayField
from django.db import models


class Question(models.Model):
    class Meta:
        db_table = "care_question"

    question = models.TextField()
    program_label = ArrayField(models.TextField(), default=[])
    response_labels = ArrayField(models.TextField())
    response_values = ArrayField(models.IntegerField())
    archived = models.BooleanField(null=False, default=False)


class Course(models.Model):
    class Meta:
        db_table = "care_course"
    name = models.TextField()


class CourseItem(models.Model):
    class Meta:
        db_table = "care_course_item"
        ordering = ['scheduled_at']

    question = models.ForeignKey(Question)
    table = models.ForeignKey(Course)
    scheduled_at = models.TimeField()
