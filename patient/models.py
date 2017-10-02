
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.fields import JSONField
from django.db import models
from care.models import CourseItem
from .forms_dairy_report import DairyReportFormV1

DEFAULT_REPORT_FORM = DairyReportFormV1


class ScheduleManager(models.Manager):
    def schedule_at(self, date):
        return self.get_queryset().extra(where=(
            "(LOWER(schedule) AT TIME ZONE 'Asia/Taipei')::Date = ('%s')::Date" % (date.strftime('%Y-%m-%d'), ),))

    def today_schedule(self):
        return self.get_queryset().extra(where=(
            "(LOWER(schedule) AT TIME ZONE 'Asia/Taipei')::Date = (current_timestamp AT TIME ZONE 'Asia/Taipei')::Date",))


class ReportManager(models.Manager):
    def today(self):
        return self.get_queryset().extra(where=(
            "(report_date = (current_timestamp AT TIME ZONE 'Asia/Taipei')::Date)",)
        ).order_by("report_period")

    def yesterday(self):
        return self.get_queryset().extra(where=(
            "(report_date = ((current_timestamp - interval '1 day') AT TIME ZONE 'Asia/Taipei')::Date)",)
        ).order_by("report_period")


class Profile(models.Model):
    class Meta:
        db_table = "patient_profile"

    name = models.TextField()
    birthday = models.DateField(null=True)
    extend = JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    customers = models.ManyToManyField(to='customer.Profile',
                                       through='Guardian',
                                       through_fields=('patient', 'customer'),
                                       related_name='patients')
    managers = models.ManyToManyField(to='employee.Profile',
                                      through='Manager',
                                      through_fields=('patient', 'employee'),
                                      related_name='patients')

    def today_courses(self):
        return self.course_schedule.extra(where=("(weekly_mask & 1 << EXTRACT(DOW FROM current_timestamp AT TIME ZONE 'Asia/Taipei')::int) > 0", ))

    def __str__(self):
        return "%i#病患 %s" % (self.id, self.name)


class Guardian(models.Model):
    class Meta:
        db_table = "patient_guardian"
        unique_together = ('patient', 'customer')

    patient = models.ForeignKey(Profile)
    customer = models.ForeignKey("customer.Profile")
    relation = models.TextField(null=True)


class Manager(models.Model):
    class Meta:
        db_table = "patient_manager"
        unique_together = ('patient', 'employee')

    patient = models.ForeignKey(Profile)
    employee = models.ForeignKey("employee.Profile")
    relation = models.TextField()


class CourseSchedule(models.Model):
    class Meta:
        db_table = "patient_course_table"

    patient = models.ForeignKey(Profile, related_name="course_schedule")
    table = models.ForeignKey("care.Course")
    weekly_mask = models.IntegerField()


class SpecialCourseSchedule(models.Model):
    class Meta:
        db_table = "patient_special_course_table"

    patient = models.ForeignKey(Profile, related_name="special_course_schedule")
    employee = models.ForeignKey("employee.Profile")
    date = models.DateField()


class NursingSchedule(models.Model):
    class Meta:
        db_table = "patient_nursing_schedule"

    objects = ScheduleManager()

    patient = models.ForeignKey(Profile, related_name='nursing_schedule')
    employee = models.ForeignKey("employee.Profile", related_name='nursing_schedule')
    schedule = DateTimeRangeField()
    flow_control = models.DateTimeField(null=True)

    def fetch_next_question(self):
        courses_id = self.patient.today_courses().values_list('table_id', flat=True)
        items = CourseItem.objects.filter(table_id__in=courses_id).extra(
            where=("care_course_item.scheduled_at > (SELECT (flow_control AT TIME ZONE 'Asia/Taipei')::Time FROM patient_nursing_schedule WHERE id = %i)" % self.id,
                   "care_course_item.scheduled_at <= (SELECT (UPPER(schedule) AT TIME ZONE 'Asia/Taipei')::Time FROM patient_nursing_schedule WHERE id = %i)" % self.id)
        ).select_related("question").order_by('scheduled_at')
        t = None
        for it in items:
            if not t:
                yield it
                t = it.scheduled_at
            elif it.scheduled_at == t:
                yield it
            else:
                return


class CareDairlyReport(models.Model):
    class Meta:
        db_table = 'patient_dairly_report'
        unique_together = ('patient', 'report_date', 'report_period')

    objects = ReportManager()

    patient = models.ForeignKey(Profile)
    report_date = models.DateField()
    report_period = models.IntegerField()
    report_version = models.IntegerField(default=1)
    report = JSONField()

    filled_by = models.ForeignKey("employee.Profile", related_name="+")
    reviewed_by = models.ForeignKey("employee.Profile", related_name="+", null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def get_period_label(cls, period):
        return '午' if period < 13 else '晚'

    @classmethod
    def is_manager(cls, employee_id, patient_id):
        return employee_id and Manager.objects.filter(patient_id=patient_id, employee_id=employee_id).exists()

    @classmethod
    def is_nurse(cls, employee_id, patient_id, date):
        return employee_id and NursingSchedule.objects.schedule_at(date).filter(patient_id=patient_id, employee_id=employee_id)

    @classmethod
    def is_guardian(cls, customer_id, patient_id):
        return customer_id and Guardian.objects.filter(patient_id=patient_id, customer_id=customer_id).exists()

    @property
    def report_form(self):
        return DEFAULT_REPORT_FORM

    def period_label(self):
        return self.get_period_label(self.report_period)

    def to_form(self):
        if self.report:
            reverse_mapping = {}
            for field_id, field in self.report_form.declared_fields.items():
                reverse_mapping[field_id] = self.report.get(field.label)
            return self.report_form(initial=reverse_mapping)
        else:
            return self.report_form()

    def from_form(self, form):
        reverse_mapping = {}
        for field_id, field in self.report_form.declared_fields.items():
            reverse_mapping[field.label] = form.cleaned_data[field_id]
        self.report = reverse_mapping


class CareHistory(models.Model):
    class Meta:
        db_table = "patient_care_history"

    patient = models.ForeignKey(Profile)
    question = models.ForeignKey("care.Question")
    answer_int = models.IntegerField(null=True)
    answer_str = models.TextField(null=True)
    routine = models.BooleanField()
    employee = models.ForeignKey("employee.Profile", related_name='+', null=True)
    scheduled_at = models.DateField()
    answered_at = models.DateTimeField(auto_now_add=True)
