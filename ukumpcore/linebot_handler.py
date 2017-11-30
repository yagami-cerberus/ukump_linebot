
from django.views.decorators.csrf import csrf_exempt
from django.db.models.functions import Now
from django.db.models import signals
from django.core.cache import cache
from django.dispatch import receiver
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.db import connection, transaction
import json

from linebot import WebhookHandler
from linebot.models import (
    MessageEvent, PostbackEvent, FileMessage, LocationMessage, TextMessage, TextSendMessage, PostbackTemplateAction, ConfirmTemplate,
    TemplateSendMessage, ButtonsTemplate, CarouselTemplate, CarouselColumn, URITemplateAction, MessageTemplateAction
)

from . import linebot_emergency, linebot_patients, linebot_report, linebot_simplequery, linebot_nursing, linebot_customer
from ukumpcore.linebot_utils import line_bot, NotMemberError, LineMessageError, is_system_admin
from patient.models import CareDailyReport
from employee.models import LineMessageQueue as EmployeeLineMessageQueue
from customer.models import LineMessageQueue as CustomerLineMessageQueue

handler = WebhookHandler(settings.LINEBOT_ACCESS_SECRET)


def line_error_handler(fn):
    def wrapper(event):
        try:
            fn(event)
        except NotMemberError:
            if event.source.type == "user":
                line_bot.reply_message(
                    event.reply_token,
                    TextSendMessage('請先加入會員\n\n%s' % settings.SITE_ROOT + reverse('line_association')))
        except LineMessageError as err:
            print("Error", event)
            if event.source.type == "user":
                line_bot.reply_message(
                    event.reply_token,
                    TextSendMessage(err.args[0]))
    return wrapper


@csrf_exempt
def linebot_handler(request):
    signature = request.META['HTTP_X_LINE_SIGNATURE']
    handler.handle(request.body.decode(), signature)
    flush_messages_queue()
    return HttpResponse("")


def _build_linebot_action(data):
    action_type = data['type']
    if action_type == 'postback':
        return PostbackTemplateAction(data['label'], data['data'])
    elif action_type == 'url':
        return URITemplateAction(data['label'], data['url'])
    elif action_type == 'message':
        return MessageTemplateAction(data['label'], data['message'])
    else:
        return MessageTemplateAction('??', json.dumps(data))


@transaction.atomic
def flush_message(record):
    data = json.loads(record.message)
    line_id = record.get_line_ids().first()
    if not line_id:
        record.delete()
        return

    message_type = data.pop('M')

    if message_type == 'buttons':
        text = data['text']
        title = data.get('title')
        alt = data.get('alt') or title or text
        if title:
            title = title[:40]
            text = text[:60]
        else:
            text = text[:160]

        line_bot.push_message(line_id, TemplateSendMessage(
            alt_text=alt,
            template=ButtonsTemplate(
                title=title,
                text=text, actions=[_build_linebot_action(a) for a in data['actions']][:4]))
        )

    elif message_type == 't':
        line_bot.push_message(line_id, TextSendMessage(data['text'][:400]))

    elif message_type == 'carousel':
        alt = data.get('alt', '有卡片可以檢視')
        max_actions = 1
        columns = []
        for col in data['columns']:
            text = col['text'] or 'NOTEXT'
            title = col.get('title')
            if title:
                title = title[:40]
                text = text[:60]
            else:
                text = text[:160]
            cc = CarouselColumn(thumbnail_image_url=col['imgurl'], title=title, text=text,
                                actions=[_build_linebot_action(a) for a in col['actions']][:3])
            max_actions = max(max_actions, len(cc.actions))
            columns.append(cc)

        line_bot.push_message(line_id, TemplateSendMessage(
            alt_text=alt,
            template=CarouselTemplate(columns=columns)))

    elif message_type == 'confirm':
        text = data['text']
        title = data.get('title')
        alt = data.get('alt') or title or text
        if title:
            title = title[:40]
            text = text[:60]
        else:
            text = text[:160]

        line_bot.push_message(line_id, TemplateSendMessage(
            alt_text=alt,
            template=ConfirmTemplate(
                title=title,
                text=text, actions=[_build_linebot_action(a) for a in data['actions']][:2]))
        )

    elif message_type == 'u':
        line_actions = [URITemplateAction(label, value) for label, value in data['u']]
        line_bot.push_message(line_id, TemplateSendMessage(
            alt_text=data['t'],
            template=ButtonsTemplate(text=data['t'], title=data.get('tt'), actions=line_actions)))

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
    if event.source.type != 'user':
        return

    resp = json.loads(event.postback.data)
    target = resp['T']

    if target == linebot_patients.T_PATIENT:
        linebot_patients.handle_postback(line_bot, event, resp)
    elif target == linebot_emergency.T_EMERGENCY:
        linebot_emergency.handle_postback(line_bot, event, resp)
    elif target == linebot_report.T_REPORT:
        linebot_report.handle_postback(line_bot, event, resp)
    elif target == linebot_simplequery.T_SIMPLE_QUERY:
        linebot_simplequery.handle_postback(line_bot, event, resp)
    elif target == linebot_nursing.T_NURSING:
        linebot_nursing.handle_postback(line_bot, event, resp)
    elif target == 'association':
        linebot_patients.handle_association(line_bot, event, resp)
    elif target == 'attachfile':
        message_content = line_bot.get_message_content(resp['file_id'])
        if resp['catalog'] == 'schedule':
            pass
        elif resp['catalog'] == 'employee':
            pass


@handler.add(MessageEvent, message=TextMessage)
@line_error_handler
def handle_message(event):
    if event.source.type != "user":
        raise RuntimeError("Unkown line message type: %s (%s)" % (event.source.type, event))

    if event.message.text == '由康照護':
        linebot_customer.main_page(line_bot, event)
    elif event.message.text == '照護日誌':
        linebot_patients.request_daily_reports(line_bot, event)
    # elif event.message.text == '緊急通報':
    #     linebot_emergency.ignition_emergency(line_bot, event)
    elif event.message.text == '照護秘書':
        linebot_report.ignition_report(line_bot, event)
    elif event.message.text == '照護小叮嚀':
        linebot_simplequery.ignition(line_bot, event, linebot_simplequery.CATALOG_COURSE)
    elif event.message.text == '聯絡照護團隊':
        linebot_simplequery.ignition(line_bot, event, linebot_simplequery.CATALOG_CONTECT)
    else:
        key = '_line:reply:%s' % event.source.user_id
        magic = cache.get(key)
        if magic:
            cache.delete(key)
            target = magic['T']
            if target == linebot_patients.T_PATIENT:
                linebot_patients.handle_message(line_bot, event, event.message.text, magic)
            elif target == linebot_simplequery.T_SIMPLE_QUERY:
                linebot_simplequery.handle_message(line_bot, event, event.message.text, magic)
        else:
            if is_system_admin(event):
                try:
                    if event.message.text == '1':
                        flush_messages_queue()
                        line_bot.reply_message(event.reply_token, TextSendMessage(text='訊息柱列已經清空。'))
                    elif event.message.text == '2':
                        count = linebot_nursing.schedule_fixed_schedule_message()
                        line_bot.reply_message(event.reply_token, TextSendMessage(text='照護排程已處理：%s筆' % count))
                    elif event.message.text == '3':
                        linebot_patients.prepare_dairly_cards()
                        line_bot.reply_message(event.reply_token, TextSendMessage(text='所有客戶卡片已經送出'))
                    elif event.message.text == '9':
                        line_bot.push_message(event.source.user_id, TextSendMessage('準備與 CRM 同步資料，這會使用一段時間...'))
                        from ukumpcore.crm.agile import sync_patients, sync_customers
                        sync_patients()
                        sync_customers()
                        line_bot.reply_message(event.reply_token, TextSendMessage(text='CRM 資料已更新完成'))
                    elif event.message.text == '0':
                        line_bot.reply_message(event.reply_token, TextSendMessage(
                            text='命令清單:\n'
                                 '1 - 立刻清空訊息柱列\n'
                                 '2 - 立刻檢查照護排程清單\n'
                                 '3 - 立刻送出客戶卡片\n'
                                 '9 - 從 CRM 更新個案資料'))
                except Exception as err:
                    line_bot.reply_message(event.reply_token, TextSendMessage(text='處理命令時發生錯誤：%s' % err))
                    raise
            else:
                raise LineMessageError(event.source.user_id)


@handler.add(MessageEvent, message=LocationMessage)
@line_error_handler
def handle_location(event):
    pass


@handler.add(MessageEvent, message=FileMessage)
@line_error_handler
def handle_attachment_file(event):
    if is_system_admin(event):
        file_id = event.message.id

        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text='請選擇檔案處理方式',
            template=ButtonsTemplate(
                title='請選擇檔案處理方式',
                text='檔案: %s' % event.message.file_name,
                actions=(
                    PostbackTemplateAction('班表', json.dumps({'T': 'attachfile', 'file_id': file_id, 'catalog': 'schedule'})),
                    PostbackTemplateAction('員工清單', json.dumps({'T': 'attachfile', 'file_id': file_id, 'catalog': 'employee'})),
                ))))


@receiver([signals.post_save], sender=CareDailyReport)
def save_care_dairly_report(sender, instance, created, **kwargs):
    if created:
        review_url = settings.SITE_ROOT + reverse('patient_daily_report', args=(instance.patient_id, instance.report_date, instance.report_period))
        title = '%s 的日報正在等待審核' % instance.patient.name
        text = '日期 %s\n照服員 %s\n' % (instance.report_date, instance.filled_by.name)
        message = json.dumps({
            'M': 'buttons',
            'title': title,
            'alt': title,
            'text': text,
            'actions': ({'type': 'url', 'label': '審核', 'url': review_url}, )
        })
        for employee_id in instance.patient.manager_set.all().values_list('employee_id', flat=True):
            EmployeeLineMessageQueue(
                employee_id=employee_id,
                scheduled_at=Now(),
                message=message).save()
    elif instance.reviewed_by:
        pass


@receiver([signals.post_save], sender=EmployeeLineMessageQueue)
@receiver([signals.post_save], sender=CustomerLineMessageQueue)
def flush_message_while_saving(sender, instance, created, **kwargs):
    if not isinstance(instance.scheduled_at, timezone.datetime) or instance.scheduled_at.tzinfo is None:
        instance.refresh_from_db()

    if instance.scheduled_at < timezone.now():
        flush_message(instance)
