
from django.views.decorators.csrf import csrf_exempt
from django.db.models.functions import Now
from django.core.cache import cache
from django.db.models import signals
from django.dispatch import receiver
from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.db import connection, transaction
from binascii import b2a_hex
import json
import os

from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, PostbackEvent, LocationMessage, TextMessage, TextSendMessage, PostbackTemplateAction,
    TemplateSendMessage, ButtonsTemplate, CarouselTemplate, CarouselColumn, URITemplateAction
)

from . import linebot_emergency, linebot_nursing, nursing_scheduler
from patient.models import CareDairlyReport
from employee.models import Profile as Employee, LineMessageQueue as EmployeeLineMessageQueue
from customer.models import LineMessageQueue as CustomerLineMessageQueue


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
            print("Error", event)
            if event.source.type == "user":
                line_bot.reply_message(event.reply_token, TextSendMessage(err.args[0]))
    return wrapper


@csrf_exempt
def linebot_handler(request):
    signature = request.META['HTTP_X_LINE_SIGNATURE']
    handler.handle(request.body.decode(), signature)
    flush_messages_queue()
    return HttpResponse("")


@transaction.atomic
def flush_message(record):
    data = json.loads(record.message)
    line_id = record.get_line_ids().first()
    if not line_id:
        record.delete()
        return

    message_type = data.pop("M")

    if message_type == "q":
        action_type = data.pop("T")
        question = data["t"]
        answers = data["q"]
        session = b2a_hex(os.urandom(16)).decode()

        line_actions = [PostbackTemplateAction(
            label,
            json.dumps({"S": session, "T": action_type, "V": value})) for label, value in answers]

        employee_id = record.employee_id
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
        line_actions = [URITemplateAction(label, value) for label, value in data["u"]]
        line_bot.push_message(line_id, TemplateSendMessage(
            alt_text=data["t"],
            template=ButtonsTemplate(text=data["t"], actions=line_actions)))

    elif message_type == "c":
        columns = []
        for col in data['col']:
            actions = []
            for a in col['a']:
                if a[0] == 'u':
                    actions.append(URITemplateAction(a[1], a[2]))
                elif a[0] == 'p':
                    actions.append(PostbackTemplateAction(a[1], a[2]))

            columns.append(CarouselColumn(thumbnail_image_url=col['url'], text=col['text'] or 'NOTEXT', actions=actions))
        template = TemplateSendMessage(alt_text=data['alt'], template=CarouselTemplate(columns=columns))
        line_bot.push_message(line_id, template)
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

        records = CustomerLineMessageQueue.objects.padding_message()
        for record in records:
            flush_message(record)
    finally:
        c.execute('select pg_advisory_unlock_all();')


@handler.add(PostbackEvent)
@line_error_handler
def handle_postback(event):
    if event.source.type != "user":
        return

    resp = json.loads(event.postback.data)

    session = resp.get("S")
    value = resp.get("V")

    if session:
        cache_data = cache.get('_line_postback:%s' % session)

        if not cache_data:
            raise LineMessageError("此操作選項已經逾期")

        session_data = json.loads(cache_data)
        employee = Employee.objects.filter(linebotintegration__lineid=event.source.user_id).first()
        # customer_id = None

        if session_data.get("employee_id") == employee.id:
            if resp["T"] == nursing_scheduler.T_CARE_QUESTION_POSTBACK:
                schedule, cont = nursing_scheduler.postback_nursing_question(employee, session_data, value)
                line_bot.reply_message(event.reply_token, TextSendMessage(text="問題 %s 已歸檔" % session_data['data']['t']))
                if cont:
                    nursing_scheduler.schedule_nursing_question(schedule)
            elif resp["T"] == nursing_scheduler.T_NUSRING_BEGIN:
                nursing_scheduler.postback_nursing_begin(employee, session_data, value)
                if value:
                    line_bot.reply_message(event.reply_token, TextSendMessage(text="行程已確認"))
                else:
                    line_bot.reply_message(event.reply_token, TextSendMessage(text="已將行程撤銷訊息轉送至照護經理"))
            else:
                raise LineMessageError("無效的回應訊息 BAD_T")
        else:
            line_bot.reply_message(event.reply_token, TextSendMessage(text="無效的回應訊息 (C)"))
    elif resp["T"] == nursing_scheduler.T_CONTECT:
        linebot_nursing.contect_manager(line_bot, event, resp)
    elif resp["T"] == linebot_nursing.T_PHONE:
        linebot_nursing.contect_phone(line_bot, event, resp)
    elif resp["T"] == linebot_emergency.T_EMERGENCY:
        linebot_emergency.handle_postback(line_bot, event, resp)


@handler.add(MessageEvent, message=TextMessage)
@line_error_handler
def handle_message(event):
    if event.source.type != "user":
        raise RuntimeError("Unkown line message type: %s (%s)" % (event.source.type, event))

    if event.message.text == '緊急通報':
        linebot_emergency.ignition_emergency(line_bot, event)
    elif event.message.text == '最新日報':
        linebot_nursing.request_cards(line_bot, event)
    elif event.message.text == '1':
        flush_messages_queue()
    elif event.message.text == '2':
        nursing_scheduler.schedule_fixed_schedule_message()
    elif event.message.text == '3':
        linebot_nursing.prepare_dairly_cards()
        raise LineMessageError("卡片準備完成")
    else:
        raise LineMessageError(event.source.user_id)


@handler.add(MessageEvent, message=LocationMessage)
@line_error_handler
def handle_location(event):
    pass


@receiver([signals.post_save], sender=CareDairlyReport)
def save_care_dairly_report(sender, instance, created, **kwargs):
    if created:
        review_url = settings.SITE_ROOT + reverse('patient_dairly_report', args=(instance.patient_id, instance.report_date, instance.report_period))
        message = json.dumps({
            'M': 'u',
            't': '%s 的日報正在等待審核' % instance.patient.name,
            'u': (('審核', review_url), )
        })
        for employee_id in instance.patient.manager_set.all().values_list('employee_id', flat=True):
            EmployeeLineMessageQueue(
                employee_id=employee_id,
                scheduled_at=Now(),
                message=message).save()
    elif instance.reviewed_by:
        pass
