
from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models.functions import Cast, TruncDate, Lower, Upper
from django.db.models import F, Max
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
from django.db import models
import pytz
import json

from patient.models import Profile as Patient, CareDailyReport

dt_field = models.DateTimeField()


class Command(BaseCommand):
    help = 'Send report warning'

    def handle(self, *args, **options):
        timezone.activate(pytz.timezone(settings.TIME_ZONE))
        now = timezone.localtime()
        date = timezone.localdate()

        patients = Patient.objects.annotate(
            nursing_schedule__date=TruncDate(Cast(Lower('nursing_schedule__schedule'), dt_field)),
            ends_at=Max(Upper('nursing_schedule__schedule')),
            form_masks=ArrayAgg(F('course_schedule__weekly_mask').bitand(1 << (date.isoweekday() % 7))),
            form_ids=ArrayAgg(F('course_schedule__table__report')),
        ).filter(
            nursing_schedule__date=date
        )

        reports_map = {}
        for r in CareDailyReport.objects.filter(report_date=timezone.localdate()):
            reports_map[r.patient_id] = r

        for patient in patients:
            if (now - patient.ends_at).total_seconds() < 1800:
                continue

            reports = set(map(lambda n: n[1], filter(lambda m: m[0] > 0, zip(patient.form_masks, patient.form_ids))))
            if len(reports) == 1:
                r = reports_map.get(patient.id)
                if not r:
                    url = settings.SITE_ROOT + reverse('patient_daily_report',
                                                       args=(patient.id, date, 18))
                    for n in patient.nursing_schedule.today():
                        n.employee.push_raw_message(json.dumps({
                            'M': 'u',
                            'tt': '[重要提醒]',
                            't': '本日 %s 日報表尚未填寫請儘速填寫' % date.strftime('%Y年%m月%d日'),
                            'u': (('填寫', url), )}))
                    for ep in patient.managers.filter(manager__relation='照護經理'):
                        ep.push_message('[重要提醒]\n照護員尚未填寫個案 %s 日報表' % patient.name)

                elif not r.reviewed_by_id and (now - r.created_at).total_seconds() < 600:
                    review_url = settings.SITE_ROOT + reverse('patient_daily_report', args=(patient.id, r.report_date, r.report_period))
                    title = '[重要提醒] %s 的日報正在等待審核' % patient.name
                    text = '日期 %s\n照服員 %s\n' % (r.report_date, r.filled_by.name)
                    message = json.dumps({
                        'M': 'buttons',
                        'title': title,
                        'alt': title,
                        'text': text,
                        'actions': ({'type': 'url', 'label': '審核', 'url': review_url}, )
                    })
                    for ep in patient.managers.filter(manager__relation='照護經理'):
                        ep.push_raw_message(message)
