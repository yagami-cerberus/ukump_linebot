
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.fields import JSONField
from django.db.models.functions import Cast, TruncDate, Lower
from django.utils.timezone import localdate, timedelta
# from django.db.models import signals
# from django.dispatch import receiver
from django.conf import settings
from django.db import models

from care.models import CourseQuestion

dt_field = models.DateTimeField()


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
    birthday = models.DateField(null=True, blank=True)
    extend = JSONField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    customers = models.ManyToManyField(to='customer.Profile',
                                       through='Guardian',
                                       through_fields=('patient', 'customer'),
                                       related_name='patients')
    managers = models.ManyToManyField(to='employee.Profile',
                                      through='Manager',
                                      through_fields=('patient', 'employee'),
                                      related_name='patients')

    def __str__(self):
        return "%s#個案 %s" % (self.id, self.name)


class DummyNote(models.Model):
    class Meta:
        db_table = "patient_note"

    patient = models.ForeignKey(Profile)
    name = models.TextField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Guardian(models.Model):
    class Meta:
        db_table = "patient_guardian"
        unique_together = ('patient', 'customer')

    patient = models.ForeignKey(Profile)
    customer = models.ForeignKey("customer.Profile")
    master = models.BooleanField(null=False, default=False)
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

    def __str__(self):
        return "%s#個案課程 %s" % (self.id, self.table.name)


class ScheduleManager(models.Manager):
    def schedule_at(self, date):
        return self.get_queryset().extra(where=(
            "(LOWER(schedule) AT TIME ZONE 'Asia/Taipei')::Date = ('%s')::Date" % (date.strftime('%Y-%m-%d'), ),))

    def today_schedule(self):
        return self.get_queryset().extra(where=(
            "(LOWER(schedule) AT TIME ZONE 'Asia/Taipei')::Date = (current_timestamp AT TIME ZONE 'Asia/Taipei')::Date",))

    def scheduled_at(self, date):
        return self.get_queryset().annotate(date=TruncDate(Cast(Lower('schedule'), dt_field))).filter(date=date)

    def today(self):
        return self.scheduled_at(localdate())

    def tomorrow(self):
        return self.scheduled_at(localdate() + timedelta(days=1))


class NursingSchedule(models.Model):
    class Meta:
        db_table = "patient_nursing_schedule"

    objects = ScheduleManager()

    patient = models.ForeignKey(Profile, related_name='nursing_schedule')
    employee = models.ForeignKey("employee.Profile", related_name='nursing_schedule')
    schedule = DateTimeRangeField()
    flow_control = models.DateTimeField(null=True)

    def today_courses(self):
        return self.patient.course_schedule.extra(
            where=("(weekly_mask & 1 << EXTRACT(DOW FROM current_timestamp AT TIME ZONE 'Asia/Taipei')::int) > 0", ))

    def fetch_next_question(self):
        courses_id = self.patient.course_schedule.extra(
            where=("(weekly_mask & 1 << EXTRACT(DOW FROM current_timestamp AT TIME ZONE 'Asia/Taipei')::int) > 0", )
        ).values_list('table_id', flat=True)
        items = CourseQuestion.objects.filter(table_id__in=courses_id).extra(
            where=("care_course_question.scheduled_at > (SELECT (flow_control AT TIME ZONE 'Asia/Taipei')::Time FROM patient_nursing_schedule WHERE id = %i)" % self.id,
                   "care_course_question.scheduled_at <= (SELECT (UPPER(schedule) AT TIME ZONE 'Asia/Taipei')::Time FROM patient_nursing_schedule WHERE id = %i)" % self.id)
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

    def __str__(self):
        return "%s#班表 %s/%s@%s" % (self.id, self.patient, self.employee, self.schedule.lower)


class CareDailyReport(models.Model):
    class Meta:
        db_table = 'patient_daily_report'
        unique_together = ('patient', 'report_date', 'report_period')

    objects = ReportManager()
    patient = models.ForeignKey(Profile)
    form_id = models.TextField(null=True, blank=True)
    report_date = models.DateField()
    report_period = models.IntegerField()
    report = JSONField()

    filled_by = models.ForeignKey("employee.Profile", related_name="+")
    reviewed_by = models.ForeignKey("employee.Profile", related_name="+", null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def get_report(cls, patient_id, report_date, report_period):
        return cls.objects.filter(patient_id=patient_id, report_date=report_date, report_period=report_period).first()

    @classmethod
    def get_form_id(cls, patient_id, employee_id, report_date):
        schedule = NursingSchedule.objects.schedule_at(report_date).filter(patient_id=patient_id, employee_id=employee_id)
        if len(schedule) != 1:
            raise RuntimeError('找到重複的排程，請聯絡系統管理員。')
        form_ids = schedule.first().today_courses().exclude(table__report__isnull=True).values_list('table__report', flat=True)
        if form_ids.count() == 0:
            raise RuntimeError('沒有可用的報表，請聯絡系統管理員。')
        elif form_ids.count() > 1:
            raise RuntimeError('找到重複的報表，請聯絡系統管理員。')
        return form_ids.first()

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
    def form_name(self):
        return settings.CARE_REPORTS.get(self.form_id, {}).get('label', '無名稱日報表')


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


class UkumpGlobal(models.Model):
    class Meta:
        db_table = "ukump_global"

    key = models.CharField(max_length=50, primary_key=True)
    value = JSONField()
