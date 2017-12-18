
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
import pytz

from patient.models import NursingSchedule


class Command(BaseCommand):
    help = 'Send report warning'

    def handle(self, *args, **options):
        timezone.activate(pytz.timezone(settings.TIME_ZONE))
        now = timezone.localtime()

        for sch in NursingSchedule.objects.today():
            if sch.flow_control and sch.flow_control < sch.schedule.lower and (now - sch.schedule.lower).seconds > 1800:
                for ep in sch.patient.managers.filter(manager__relation='照護經理'):
                    ep.push_message('照護員 %s 尚未確認個案 %s 的照護行程' % (sch.employee.name, sch.patient.name))
