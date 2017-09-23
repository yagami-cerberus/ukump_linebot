
from django.utils import timezone, dateparse
from django.conf import settings
from django.urls import reverse
from django.db import transaction
from datetime import time, timedelta
import json
import pytz

from employee.models import LineMessageQueue as EmployeeLineMessageQueue
from patient.models import NursingSchedule, CareHistory

fix_tz = pytz.timezone('Etc/GMT-8')

NOON = time(12, 30)
NIGHT = time(18, 00)
T_NUSRING_BEGIN = "NCBEGIN"
T_CARE_QUESTION_POSTBACK = "NCQUESP"


def create_datetime(date, time):
    return timezone.datetime(date.year, date.month, date.day, time.hour, time.minute, 0, 0, fix_tz)


@transaction.atomic
def schedule_fixed_schedule_message():
    for schedule in NursingSchedule.objects.today_schedule().extra({"localbegin": "LOWER(schedule) AT TIME ZONE 'Asia/Taipei'"}).filter(flow_control=None):
        message = {
            "T": T_NUSRING_BEGIN,
            "M": "q",
            "s": schedule.pk,
            "t": "本日行程\n照護 %s 在 %s 點 %s 分" % (schedule.patient.name, schedule.localbegin.hour, schedule.localbegin.minute),
            "q": (("確認", True), ("撤銷", False))
        }

        EmployeeLineMessageQueue(employee=schedule.employee,
                                 scheduled_at=schedule.schedule.lower - timedelta(minutes=15),
                                 message=json.dumps(message)).save()

        now = timezone.now().astimezone(fix_tz)
        t_noon = create_datetime(now, NOON)
        t_night = create_datetime(now, NIGHT)

        noon_message = '日報表填寫 %s%s' % (settings.SITE_ROOT, reverse('patient_dairly_report', schedule.patient_id, t_noon.date(), 12))
        EmployeeLineMessageQueue(employee=schedule.employee,
                                 scheduled_at=t_noon,
                                 message=json.dumps({'M': 't', 't': noon_message})).save()

        night_message = '日報表填寫 %s%s' % (settings.SITE_ROOT, reverse('patient_dairly_report', schedule.patient_id, t_noon.date(), 18))
        EmployeeLineMessageQueue(employee=schedule.employee,
                                 scheduled_at=t_night,
                                 message=json.dumps({'M': 't', 't': night_message})).save()

        schedule.flow_control = schedule.schedule.lower
        schedule.save()


@transaction.atomic
def schedule_nursing_question(schedule):
    schedule.model.objects.filter(pk=schedule.pk).select_for_update(nowait=True)
    items = tuple(schedule.fetch_next_question())
    now = timezone.now().astimezone(fix_tz)

    for it in items:
        scheduled_at = create_datetime(now, it.scheduled_at)
        message = {
            "T": T_CARE_QUESTION_POSTBACK,
            "M": "q",
            "s": schedule.pk,
            "p": schedule.patient_id,
            "qid": schedule.question_id,
            "sch": scheduled_at.isoformat(),
            "r": True,
            "t": it.question.question,
            "q": tuple(zip(it.question.response_labels, it.question.response_values))
        }
        EmployeeLineMessageQueue(employee=schedule.employee,
                                 scheduled_at=scheduled_at,
                                 message=json.dumps(message)).save()
        schedule.flow_control = scheduled_at
        schedule.save()


@transaction.atomic
def postback_nursing_question(employee, session_data, value):
    schedule = NursingSchedule.objects.get(pk=session_data['s'])
    question_id = session_data['qid']
    routine = session_data['r']

    if isinstance(value, int):
        ans_int, ans_str = value, None
    else:
        ans_int, ans_str = None, value

    CareHistory(patient=schedule.patient_id, employee=employee, question_id=question_id,
                answer_int=ans_int, answer_str=ans_str, routine=routine).save()
    return schedule, (dateparse.parse_datetime(session_data['sch'] == schedule.flow_control))
