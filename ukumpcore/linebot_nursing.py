
from collections import namedtuple
import json
import pytz

from django.utils.crypto import get_random_string
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
from django.db import transaction
from datetime import time, timedelta
from linebot.models import TextSendMessage

from ukumpcore.linebot_utils import LineMessageError, get_employee
from employee.models import Profile as Employee, LineMessageQueue as EmployeeLineMessageQueue
from patient.models import NursingSchedule, CareHistory

fix_tz = pytz.timezone('Etc/GMT-8')

NOON = time(12, 30)
NIGHT = time(17, 30)
PostbackCache = namedtuple('PostbackCache', ('schedule_id', 'question_id', 'scheduled_at', 'routine'))
T_NURSING = 'T_N'

STAGE_BEGIN = 'begin'
STAGE_QUESTION_POSTBACK = 'postback'


def create_datetime(date, time):
    return timezone.datetime(date.year, date.month, date.day, time.hour, time.minute, 0, 0, fix_tz)


@transaction.atomic
def schedule_fixed_schedule_message():
    count = 0
    for schedule in NursingSchedule.objects.today_schedule().extra({"localbegin": "LOWER(schedule) AT TIME ZONE 'Asia/Taipei'"}).filter(flow_control=None):
        message = {
            'M': 'buttons',
            'alt': '%s 本日行程提醒' % schedule.localbegin.strftime('%Y年%m月%d日'),
            'title': '%s 本日行程' % schedule.localbegin.strftime('%Y年%m月%d日'),
            'text': '%s 照護 在 %s 點 %s 分' % (schedule.patient.name, schedule.localbegin.hour, schedule.localbegin.minute),
            'actions': (
                {'type': 'postback', 'label': '確認行程', 'data': json.dumps({'T': T_NURSING, 'S': '', 'stage': STAGE_BEGIN, 'V': (schedule.pk, True)})},
                {'type': 'postback', 'label': '回報行程錯誤', 'data': json.dumps({'T': T_NURSING, 'S': '', 'stage': STAGE_BEGIN, 'V': (schedule.pk, False)})},
            )
        }

        EmployeeLineMessageQueue(employee=schedule.employee,
                                 scheduled_at=schedule.schedule.lower - timedelta(minutes=15),
                                 message=json.dumps(message)).save()

        schedule.flow_control = schedule.schedule.lower - timedelta(minutes=15)
        schedule.save()
        count += 1
    return count


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
                session = get_random_string(32)
                postback_cache = PostbackCache(schedule.id, it.question.id, scheduled_at, True)
                cache.add('_nursing_postback:%s' % session, postback_cache, timeout=57600)

                has_q = True
                message = {
                    'M': 'buttons',
                    'alt': '照護提醒',
                    'title': '%s ' % scheduled_at.strftime('%Y-%m-%d %H:%M'),
                    'text': it.question.question,
                    'actions': [
                        {'type': 'postback',
                         'label': label,
                         'data': json.dumps({'T': T_NURSING, 'S': '', 'stage': STAGE_QUESTION_POSTBACK,
                                             'V': (session, it.question.question, value)})}
                        for label, value in zip(it.question.response_labels, it.question.response_values)
                    ]
                }
            else:
                message = {
                    'M': 't',
                    'text': it.question.question
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
def nursing_begin(line_bot, event, value):
    sch_id, is_begin = value
    schedule = NursingSchedule.objects.extra({"localbegin": "LOWER(schedule) AT TIME ZONE 'Asia/Taipei'"}).get(pk=sch_id)

    if schedule.employee != get_employee(event):
        raise LineMessageError('身份錯誤')

    now = timezone.now()
    if (schedule.schedule.lower - now).total_seconds() > 3600 or (now - schedule.schedule.upper).total_seconds() > 1800:
        raise LineMessageError('時間錯誤，不在可回應時間內。')

    if is_begin:
        if schedule.flow_control < schedule.schedule.lower:
            line_bot.reply_message(event.reply_token, TextSendMessage(text='行程已確認開始'))

            url = settings.SITE_ROOT + reverse('patient_daily_report',
                                               args=(schedule.patient_id, schedule.localbegin.date(), 18))
            EmployeeLineMessageQueue(employee=schedule.employee,
                                     scheduled_at=schedule.schedule.upper,
                                     message=json.dumps({'M': 'u',
                                                         't': '請填寫 %s 日報表' % schedule.localbegin.strftime('%Y年%m月%d日'),
                                                         'u': (('填寫', url), )})).save()
            schedule_nursing_question(schedule)
        else:
            line_bot.reply_message(event.reply_token, TextSendMessage(text='行程已開始'))
    else:
        text = '照護員 %s 回報取消今日對 %s 照護行程' % (schedule.employee.name, schedule.patient.name)
        for employee in Employee.objects.filter(manager__patient=schedule.patient, manager__relation='照護經理'):
            employee.push_message(text)


@transaction.atomic
def nusring_postback(line_bot, event, value):
    session, question_text, answer = value
    postback_cache = cache.get('_nursing_postback:%s' % session)
    if postback_cache is None:
        raise LineMessageError('此操作已超過有效時間。')

    if isinstance(value, int):
        ans_int, ans_str = value, None
    else:
        ans_int, ans_str = None, value

    schedule = NursingSchedule.objects.get(pk=postback_cache.schedule_id)
    CareHistory(patient_id=schedule.patient_id, employee=get_employee(event),
                question_id=postback_cache.question_id, scheduled_at=postback_cache.scheduled_at,
                answer_int=ans_int, answer_str=ans_str, routine=postback_cache.routine).save()

    line_bot.reply_message(event.reply_token, TextSendMessage(text="問題 %s 已歸檔" % question_text))
    if postback_cache.scheduled_at == schedule.flow_control:
        schedule_nursing_question(schedule)


def handle_postback(line_bot, event, resp):
    stage, value = resp['stage'], resp.get('V')
    if stage == STAGE_QUESTION_POSTBACK:
        nusring_postback(line_bot, event, value)
    elif stage == STAGE_BEGIN:
        nursing_begin(line_bot, event, value)
