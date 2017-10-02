
from linebot.models import TemplateSendMessage, TextSendMessage, ButtonsTemplate, PostbackTemplateAction, URITemplateAction
from django.conf import settings
from django.urls import reverse
import json

from . import linebot_utils as utils

STAGE_INIGITION = 'i'
STAGE_SELECT_TARGET = 's'
STAGE_TRANSFER_CONFIRM = 'a'
STAGE_TRANSFER = 't'
STAGE_DISMISS_CONFIRM = 'dc'
STAGE_DISMISS = 'd'


ACTION_CANCEL = PostbackTemplateAction("緊急狀況解除", json.dumps({'S': '', 'T': 'emergency', 'stage': STAGE_DISMISS_CONFIRM, 'V': True}))
TEMPLATE_IGNITION = TemplateSendMessage(
    alt_text="確認緊急通報",
    template=ButtonsTemplate(text="確認緊急通報", actions=[
        PostbackTemplateAction("是", json.dumps({'S': '', 'T': 'emergency', 'stage': STAGE_INIGITION, 'V': True})),
        PostbackTemplateAction("否", json.dumps({'S': '', 'T': 'emergency', 'stage': STAGE_INIGITION, 'V': False}))]))
TEMPLATE_SELECTION = TemplateSendMessage(
    alt_text="通報對象",
    template=ButtonsTemplate(text="通報對象", actions=[
        PostbackTemplateAction("救護車/消防隊", json.dumps({'S': '', 'T': 'emergency', 'stage': STAGE_SELECT_TARGET, 'V': 110})),
        PostbackTemplateAction("警察局", json.dumps({'S': '', 'T': 'emergency', 'stage': STAGE_SELECT_TARGET, 'V': 119})),
        PostbackTemplateAction("關懷中心", json.dumps({'S': '', 'T': 'emergency', 'stage': STAGE_SELECT_TARGET, 'V': 999}))]))
TEMPLATE_DISMISS_CONFIRM = TemplateSendMessage(
    alt_text="解除緊急通報",
    template=ButtonsTemplate(text="確認解除緊急通報", actions=[
        PostbackTemplateAction("是", json.dumps({'S': '', 'T': 'emergency', 'stage': STAGE_DISMISS, 'V': True}))]))
TEMPLATE_TRANSFER_ACTION = [
    PostbackTemplateAction("確認", json.dumps({'S': '', 'T': 'emergency', 'stage': STAGE_TRANSFER, 'V': True}))]


def ignition_emergency(line_bot, event):
    line_bot.reply_message(event.reply_token, TEMPLATE_IGNITION)


def select_emergency_target(line_bot, event):
    line_bot.reply_message(event.reply_token, TEMPLATE_SELECTION)


def contact_care_center(line_bot, event):
    actions = [
        URITemplateAction("個案資訊及聯絡", settings.SITE_ROOT + reverse('line_nav', args=('emergency', ))),
        PostbackTemplateAction("轉知照護經理", json.dumps({'S': '', 'T': 'emergency', 'stage': STAGE_TRANSFER_CONFIRM, 'V': True})),
        ACTION_CANCEL]

    strftime = utils.localtime().strftime('%m/%d %H:%M')
    title = []
    body = []

    employee = utils.get_employee(event)
    if employee:
        title.append("照護員")
        body.append("照護員 %s" % employee.name)
    customer = utils.get_customer(event)
    if customer and customer.patients.count():
        title.append("家屬")
        body.append("家屬 %s" % customer.name)

    if title:
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text="%s緊急通報" % ("/".join(title)),
            template=ButtonsTemplate(text="緊急通報\n%s\n在 %s" % ("\n".join(body), strftime),
                                     actions=actions)))


def transfer_confirm(line_bot, event, value):
    line_bot.reply_message(event.reply_token, TemplateSendMessage(
        alt_text="確認轉知照護經理",
        template=ButtonsTemplate(text="確認轉知照護經理？",
                                 actions=TEMPLATE_TRANSFER_ACTION)))


def transfer(line_bot, event):
    strftime = utils.localtime().strftime('%m/%d %H:%M')

    employee = utils.get_employee(event)
    if employee:
        for schedule in employee.nursing_schedule.today_schedule().distinct("patient").select_related("patient"):
            patient = schedule.patient
            template = TemplateSendMessage(
                alt_text="照護員緊急通報",
                template=ButtonsTemplate(
                    text="照護員緊急通報\n個案: %s\n時間 %s" % (patient.name, strftime, ),
                    actions=[
                        URITemplateAction("個案資訊及聯絡", settings.SITE_ROOT + reverse('line_nav', args=('emergency', ))),
                        ACTION_CANCEL
                    ]))
            for lineid in utils.get_employees_lineid(patient.managers.filter(manager__relation="照護經理")):
                line_bot.push_message(lineid, template)

    customer = utils.get_employee(event)
    if customer:
        for patient in customer.patients.all():
            template = TemplateSendMessage(
                alt_text="家屬緊急通報",
                template=ButtonsTemplate(
                    text="家屬緊急通報\n個案: %s\n時間 %s" % (patient.name, strftime, ),
                    actions=[
                        URITemplateAction("個案資訊及聯絡", settings.SITE_ROOT + reverse('line_nav', args=('emergency', ))),
                        ACTION_CANCEL
                    ]))
            for lineid in utils.get_employees_lineid(patient.managers.filter(manager__relation="照護經理")):
                line_bot.push_message(lineid, template)


def dismiss_confirm(line_bot, event):
    line_bot.reply_message(event.reply_token, TEMPLATE_DISMISS_CONFIRM)


def dismiss(line_bot, event):
    line_bot.reply_message(event.reply_token, TextSendMessage("緊急狀況解除"))


def handle_postback(line_bot, event, stage, value):
    if stage == STAGE_INIGITION:
        if value:
            select_emergency_target(line_bot, event)
        else:
            line_bot.reply_message(event.reply_token, TextSendMessage("緊急狀況解除"))
    elif stage == STAGE_SELECT_TARGET:
        if value == 110:
            line_bot.reply_message(event.reply_token, TextSendMessage("tel://110"))
        elif value == 119:
            line_bot.reply_message(event.reply_token, TextSendMessage("tel://119"))
        elif value == 999:
            contact_care_center(line_bot, event)
    elif stage == STAGE_TRANSFER_CONFIRM:
        transfer_confirm(line_bot, event, value)
    elif stage == STAGE_TRANSFER:
        transfer(line_bot, event)
    elif stage == STAGE_DISMISS_CONFIRM:
        dismiss_confirm(line_bot, event)
    elif stage == STAGE_DISMISS:
        dismiss(line_bot, event)
