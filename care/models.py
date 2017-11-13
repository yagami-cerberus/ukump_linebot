
from django.contrib.postgres.fields import ArrayField
from django.conf import settings
from django.db import models

COURSE_REPORTS = tuple((key, opts.get('label', key)) for key, opts in settings.CARE_REPORTS.items())


class Question(models.Model):
    class Meta:
        db_table = "care_question"

    question = models.TextField()
    program_label = ArrayField(models.TextField(), default=[], blank=True)
    response_labels = ArrayField(models.TextField(), blank=True)
    response_values = ArrayField(models.IntegerField(), blank=True)
    archived = models.BooleanField(null=False, default=False)

    def __str__(self):
        return "%s#問題 %s" % (self.id, self.question)


class Course(models.Model):
    class Meta:
        db_table = "care_course"
    name = models.TextField()
    report = models.CharField(max_length=500, null=True, blank=True, choices=COURSE_REPORTS)

    def report_name(self):
        if self.report in settings.CARE_REPORTS:
            return settings.CARE_REPORTS[self.report].get('label', self.report)
        else:
            return self.report

    def __str__(self):
        return "%s#課程 %s" % (self.id, self.name)


class CourseDetail(models.Model):
    class Meta:
        db_table = "care_course_detail"
        ordering = ['scheduled_at']

    table = models.ForeignKey(Course)
    name = models.TextField()
    scheduled_at = models.TimeField()

    def __str__(self):
        return "%s#日課 %s" % (self.id, self.name)


class CourseQuestion(models.Model):
    class Meta:
        db_table = "care_course_question"
        ordering = ['scheduled_at']

    question = models.ForeignKey(Question, limit_choices_to={"archived": False})
    table = models.ForeignKey(Course)
    scheduled_at = models.TimeField()

    def __str__(self):
        return "%s#課程項目 %s (%s)" % (self.id, self.question.question, self.scheduled_at)
