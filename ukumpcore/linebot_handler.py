
from django.views.decorators.csrf import csrf_exempt
from django.db.models.functions import Now
from django.core.cache import cache
from django.db.models import signals
from django.dispatch import receiver
from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.db import connection, transaction

from . import nursing_scheduler
from patient.models import NursingSchedule, CareDairlyReport
from employee.models import Profile as Employee, LineMessageQueue as EmployeeLineMessageQueue

from datetime import timedelta
from linebot.models import MessageEvent, PostbackEvent, LocationMessage, TextMessage
from binascii import b2a_hex
import json
import os

from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    TextSendMessage, PostbackTemplateAction,
    TemplateSendMessage, ButtonsTemplate,  # PostbackTemplateAction, ConfirmTemplate
)


ACCESS_TOKEN = settings.LINEBOT_ACCESS_TOKEN
ACCESS_SECRET = settings.LINEBOT_ACCESS_SECRET

line_bot = LineBotApi(ACCESS_TOKEN)
handler = WebhookHandler(ACCESS_SECRET)


class LineMessageError(RuntimeError):
    pass


def line_error_handler(fn):
    def wrapper(event):
        try:
            fn(event)
        except LineMessageError as err:
            line_bot.reply_message(event.reply_token, TextSendMessage(err.args[0]))
    return wrapper


@csrf_exempt
def linebot_handler(request):
    signature = request.META['HTTP_X_LINE_SIGNATURE']
    handler.handle(request.body.decode(), signature)
    return HttpResponse("")


@transaction.atomic
def flush_message(record):
    data = json.loads(record.message)
    employee_id = record.employee_id
    line_id = record.employee.linebotintegration_set.first().lineid
    message_type = data.pop("M")

    if message_type == "q":
        action_type = data.pop("T")
        question = data["t"]
        answers = data["q"]
        session = b2a_hex(os.urandom(16)).decode()

        line_actions = [PostbackTemplateAction(
            label,
            json.dumps({"S": session, "T": action_type, "V": value})) for label, value in answers]

        cache.add('_line_postback:%s' % session, json.dumps({
            "catalog": action_type,
            "employee_id": employee_id,
            "data": data}), timeout=28800)

        line_bot.push_message(line_id, TemplateSendMessage(
            alt_text=question,
            template=ButtonsTemplate(text=question, actions=line_actions)))

    elif message_type == "t":
        line_bot.push_message(line_id, TextSendMessage(data["t"]))

    elif message_type == "u":
        line_bot.push_message(line_id, TextSendMessage(data["u"]))

    record.delete()


def flush_messages_queue():
    c = connection.cursor()
    c.execute('select pg_try_advisory_lock(105);')
    if c.fetchall()[0][0]is False:
        return

    try:
        records = EmployeeLineMessageQueue.objects.padding_message()
        for record in records:
            flush_message(record)
    finally:
        c.execute('select pg_advisory_unlock_all();')


# def flush_today_schedule():
#     for schedule in NursingSchedule.objects.today_schedule().extra({"localbegin": "LOWER(schedule) AT TIME ZONE 'Asia/Taipei'"}).filter(flow_control=None):
#         data = EmployeeLineMessageQueue.pack_text_message("本日行程\n照護 %s 在 %s 點 %s 分" % (schedule.patient.name, schedule.localbegin.hour, schedule.localbegin.minute))
#         EmployeeLineMessageQueue(employee=schedule.employee, scheduled_at=schedule.schedule.lower - timedelta(minutes=15), message=json.dumps(data)).save()
#         schedule.flow_control = schedule.schedule.lower
#         schedule.save()


@handler.add(PostbackEvent)
@line_error_handler
def handle_postback(event):
    if event.source.type != "user":
        return

    resp = json.loads(event.postback.data)

    session = resp["S"]
    value = resp["V"]
    cache_data = cache.get('_line_postback:%s' % session)

    if not cache_data:
        raise LineMessageError("無效的回應訊息 (BAD_S)")

    session_data = json.loads(cache_data)
    employee = Employee.objects.filter(linebotintegration__lineid=event.source.user_id).first()
    # customer_id = None

    if session_data.get("employee_id") == employee.id:
        if resp["T"] == nursing_scheduler.T_CARE_QUESTION_POSTBACK:
            schedule, cont = nursing_scheduler.postback_nursing_question(employee, session_data, value)
            if cont:
                nursing_scheduler.schedule_nursing_question(schedule)
        elif resp["T"] == nursing_scheduler.T_NUSRING_BEGIN:
            pass
        else:
            raise LineMessageError("無效的回應訊息 BAD_T")
    else:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="無效的回應訊息 (C)"))


@handler.add(MessageEvent, message=TextMessage)
@line_error_handler
def handle_message(event):
    if event.source.type != "user":
        raise RuntimeError("Unkown line message type: %s (%s)" % (event.source.type, event))

    lfm = {'意見與回饋': 'feedback', '申請加入': 'join', '緊急通報': 'sos', '本日報表': 'dairy_reports'}
    if event.message.text in lfm:
        line_bot.reply_message(event.reply_token, TextSendMessage(settings.SITE_ROOT + '/integrations/linebot/nav/%s' % lfm[event.message.text]))
    if event.message.text == '1':
        flush_messages_queue()
    elif event.message.text == '2':
        flush_today_schedule()
    raise LineMessageError(event.source.user_id)


@handler.add(MessageEvent, message=LocationMessage)
@line_error_handler
def handle_location(event):
    pass


@receiver([signals.post_save], sender=CareDairlyReport)
def save_care_dairly_report(sender, instance, created, **kwargs):
    if created:
        message = EmployeeLineMessageQueue.pack_text_message('%s 日報表等待審核:\n %s' % (
            instance.patient.name,
            settings.SITE_ROOT + reverse('patient_dairly_reports', instance.patient_id, instance.report_date, instance.report_period)))
        for employee_id in instance.patient.manager_set.all().values_list('employee_id', flat=True):
            EmployeeLineMessageQueue(
                employee_id=employee_id,
                scheduled_at=Now(),
                message=message).save()
    elif instance.reviewed_by:
        pass
