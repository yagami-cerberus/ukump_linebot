
from django.utils import timezone, dateparse
from django.conf import settings
from django.urls import reverse
from django.db import transaction
from datetime import time, timedelta
import json
import pytz

from employee.models import Profile as Employee, LineMessageQueue as EmployeeLineMessageQueue
from patient.models import NursingSchedule, CareHistory

fix_tz = pytz.timezone('Etc/GMT-8')

NOON = time(12, 30)
NIGHT = time(18, 00)
T_NUSRING_BEGIN = "NCBEGIN"
T_CARE_QUESTION_POSTBACK = "NCQUESP"
T_CONTECT = "NCCONTECT"


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

        schedule.flow_control = schedule.schedule.lower - timedelta(minutes=15)
        schedule.save()


@transaction.atomic
def schedule_nursing_question(schedule):
    NursingSchedule.objects.filter(pk=schedule.pk).select_for_update(nowait=True)
    items = tuple(schedule.fetch_next_question())

    if items:
        has_q = False
        scheduled_at = None

        for it in items:
            scheduled_at = create_datetime(schedule.flow_control.astimezone(fix_tz), it.scheduled_at)

            if it.question.response_labels:
                has_q = True
                message = {
                    "T": T_CARE_QUESTION_POSTBACK,
                    "M": "q",
                    "s": schedule.pk,
                    "p": schedule.patient_id,
                    "qid": it.question_id,
                    "sch": scheduled_at.isoformat(),
                    "r": True,
                    "t": it.question.question,
                    "q": tuple(zip(it.question.response_labels, it.question.response_values))
                }
            else:
                message = {
                    "M": "t",
                    "t": it.question.question
                }

            EmployeeLineMessageQueue(employee=schedule.employee,
                                     scheduled_at=scheduled_at,
                                     message=json.dumps(message)).save()
        schedule.flow_control = scheduled_at
        schedule.save()

        if has_q is False:
            schedule_nursing_question(schedule)
    else:
        EmployeeLineMessageQueue(employee=schedule.employee,
                                 scheduled_at=schedule.schedule.upper,
                                 message=json.dumps({'M': 't', 't': '今日 %s 照護行程已結束' % schedule.patient.name})).save()
        schedule.flow_control = schedule.schedule.upper + timedelta(seconds=1)
        schedule.save()


@transaction.atomic
def postback_nursing_begin(employee, session_data, value):
    schedule = NursingSchedule.objects.get(pk=session_data['data']['s'])
    if value:
        if schedule.flow_control < schedule.schedule.lower:
            now = timezone.now().astimezone(fix_tz)
            t_noon = create_datetime(now, NOON)
            t_night = create_datetime(now, NIGHT)

            noon_url = settings.SITE_ROOT + reverse('patient_dairly_report', args=(schedule.patient_id, t_noon.date(), 12))
            EmployeeLineMessageQueue(employee=schedule.employee,
                                     scheduled_at=t_noon,
                                     message=json.dumps({'M': 'u', 't': '上午日報表', 'u': (('填寫', noon_url), )})).save()

            night_url = settings.SITE_ROOT + reverse('patient_dairly_report', args=(schedule.patient_id, t_noon.date(), 18))
            EmployeeLineMessageQueue(employee=schedule.employee,
                                     scheduled_at=t_night,
                                     message=json.dumps({'M': 'u', 't': '下午日報表', 'u': (('填寫', night_url), )})).save()
            schedule_nursing_question(schedule)
    else:
        for employee in Employee.objects.filter(manager__patient=schedule.patient, manager__relation="照護經理"):
            EmployeeLineMessageQueue(
                employee=employee,
                scheduled_at=timezone.now(),
                message=json.dumps({'M': 't', 't': '照護員 %s 取消今日對 %s 照護行程' % (employee.name, schedule.patient.name)})).save()


@transaction.atomic
def postback_nursing_question(employee, session_data, value):
    schedule = NursingSchedule.objects.get(pk=session_data['data']['s'])
    question_id = session_data['data']['qid']
    routine = session_data['data']['r']
    sch_at = dateparse.parse_datetime(session_data['data']['sch'])

    if isinstance(value, int):
        ans_int, ans_str = value, None
    else:
        ans_int, ans_str = None, value

    CareHistory(patient_id=schedule.patient_id, employee=employee, question_id=question_id,
                scheduled_at=sch_at, answer_int=ans_int, answer_str=ans_str, routine=routine).save()
    return schedule, (sch_at == schedule.flow_control)
