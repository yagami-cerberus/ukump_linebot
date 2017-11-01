
from linebot.models import TemplateSendMessage, TextSendMessage, ButtonsTemplate, CarouselTemplate, PostbackTemplateAction, URITemplateAction, CarouselColumn
from django.core.cache import cache
from django.conf import settings
from django.urls import reverse
from time import time
import json

from ukumpcore.crm.agile import customer_support_crm
from patient.models import Profile as Patient
from . import linebot_utils as utils

T_EMERGENCY = 'T_EMERGENCY'

STAGE_INIGITION = 'i'
STAGE_INIGITION_CONFIRM = 'c'
STAGE_SELECT_TARGET = 's'
STAGE_TRANSFER_CONFIRM = 'a'
STAGE_TRANSFER = 't'
STAGE_DISMISS_CONFIRM = 'dc'
STAGE_DISMISS = 'd'


ACTION_CANCEL = PostbackTemplateAction("緊急狀況解除", json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_DISMISS_CONFIRM, 'V': True}))
TEMPLATE_DISMISS_CONFIRM = TemplateSendMessage(
    alt_text="解除緊急通報",
    template=ButtonsTemplate(text="確認解除緊急通報", actions=[
        PostbackTemplateAction("是", json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_DISMISS, 'V': True}))]))
TEMPLATE_TRANSFER_ACTION = [
    PostbackTemplateAction("確認", json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_TRANSFER, 'V': True}))]


def ignition_emergency(line_bot, event):
    employee = utils.get_employee(event)
    customer = utils.get_customer(event)

    patients = Patient.objects.none()
    if employee:
        patients |= employee.patients.all()
        patients |= Patient.objects.filter(id__in=employee.nursing_schedule.today_schedule().values_list("patient_id", flat=True))
    if customer and customer_support_crm(customer):
        patients |= customer.patients.all()

    patients = patients.distinct()

    if patients:
        l = len(patients)
        if l == 1:
            select_patient(line_bot, event, patient=patients[0])
        else:
            columns = []
            for i in range(0, l, 4):
                actions = []
                for j in range(i, min(i + 4, l)):
                    p = patients[j]
                    actions.append(PostbackTemplateAction(
                        p.name,
                        json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_INIGITION, 'V': p.id})))
                columns.append(CarouselColumn(text="請選擇緊急通報對象", actions=actions))
            line_bot.reply_message(event.reply_token, TemplateSendMessage(
                alt_text="請選擇緊急通報對象",
                template=CarouselTemplate(columns=columns)))
    elif employee:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="無法取得可通報的照護對象，請直接與照護經理聯絡。"))
    elif customer:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="無法取得可通報的照護對象，請直接與照護經理聯絡。"))
    else:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="請先註冊會員。"))


def select_patient(line_bot, event, value=None, patient=None):
    if not patient:
        patient = Patient.objects.get(pk=value)

    session_i = int(time())
    session = "_line_emergency:%s:%i" % (event.source.user_id, session_i)
    cache.set(session, patient.id, 600)
    line_bot.reply_message(event.reply_token, TemplateSendMessage(
        alt_text="緊急通報",
        template=ButtonsTemplate(
            title="緊急通報",
            text="通報案件 %s" % patient.name,
            actions=[
                URITemplateAction("確認", settings.SITE_ROOT + reverse('patient_emergency', args=(patient.id, )))
            ])
    ))


# def confirm_emergency_action(line_bot, event, value):
#     session = "_line_emergency:%s:%i" % (event.source.user_id, value['s'])
#     answer = value['a']
#     patient_id = cache.get(session)

#     employee = utils.get_employee(event)
#     customer = utils.get_customer(event)
#     if employee and employee.patients.filter(id=patient_id):
#         source = employee
#     elif customer and customer.patients.filter(id=patient_id):
#         source = customer

#     if patient_id:
#         cache.delete(session)
#         patient = Patient.objects.get(id=patient_id)
#         if answer:
#             title = "LINE 緊急通報案例: %s" % patient.name
#             message = '通報人: %s\n緊急通報對象: <a href="%s">%s</a>' % (source.name, get_patient_crm_url(patient), patient.name)
#             ticket_id = create_crm_ticket(source, title, message, emergency=True)

#             template = TemplateSendMessage(
#                 alt_text="緊急通報處置",
#                 template=ButtonsTemplate(
#                     title="緊急通報處置",
#                     text="通報案例 %s" % patient.name,
#                     actions=[
#                         PostbackTemplateAction("聯絡救護車/消防隊", json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_SELECT_TARGET, 'V': (ticket_id, 119)})),
#                         PostbackTemplateAction("聯絡警察局", json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_SELECT_TARGET, 'V': (ticket_id, 110)})),
#                         PostbackTemplateAction("聯絡關懷中心", json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_SELECT_TARGET, 'V': (ticket_id, 999)}))])
#             )
#             line_bot.reply_message(event.reply_token, template)
#         else:
#             line_bot.reply_message(event.reply_token, TextSendMessage(text="緊急通報已取消。"))
#     else:
#         line_bot.reply_message(event.reply_token, TextSendMessage(text="此操作已經失效，請重新執行緊急通報。"))


# def update_emergency_action(line_bot, event, value):
#     ticket_id, operation = value

#     if operation == 110:
#         update_crm_ticket_status()
#         line_bot.reply_message(event.reply_token, TextSendMessage("聯絡救護車/消防隊 tel://110"))
#     elif operation == 119:
#         line_bot.reply_message(event.reply_token, TextSendMessage("聯絡警察局 tel://119"))
#     elif value == 999:
#         contact_care_center(line_bot, event)


# def contact_care_center(line_bot, event):
#     actions = [
#         URITemplateAction("個案資訊及聯絡", settings.SITE_ROOT + reverse('patient_list_members')),
#         PostbackTemplateAction("轉知照護經理", json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_TRANSFER_CONFIRM, 'V': True})),
#         ACTION_CANCEL]

#     strftime = utils.localtime().strftime('%m/%d %H:%M')
#     title = []
#     body = []

#     employee = utils.get_employee(event)
#     if employee:
#         title.append("照護員")
#         body.append("照護員 %s" % employee.name)
#     customer = utils.get_customer(event)
#     if customer and customer.patients.count():
#         title.append("家屬")
#         body.append("家屬 %s" % customer.name)

#     if title:
#         line_bot.reply_message(event.reply_token, TemplateSendMessage(
#             alt_text="%s緊急通報" % ("/".join(title)),
#             template=ButtonsTemplate(text="緊急通報\n%s\n在 %s" % ("\n".join(body), strftime),
#                                      actions=actions)))


# def transfer_confirm(line_bot, event, value):
#     line_bot.reply_message(event.reply_token, TemplateSendMessage(
#         alt_text="確認轉知照護經理",
#         template=ButtonsTemplate(text="確認轉知照護經理？",
#                                  actions=TEMPLATE_TRANSFER_ACTION)))


# def transfer(line_bot, event):
#     strftime = utils.localtime().strftime('%m/%d %H:%M')

#     employee = utils.get_employee(event)
#     if employee:
#         for schedule in employee.nursing_schedule.today_schedule().distinct("patient").select_related("patient"):
#             patient = schedule.patient
#             template = TemplateSendMessage(
#                 alt_text="照護員緊急通報",
#                 template=ButtonsTemplate(
#                     text="照護員緊急通報\n個案: %s\n時間 %s" % (patient.name, strftime, ),
#                     actions=[
#                         URITemplateAction("個案資訊及聯絡", settings.SITE_ROOT + reverse('line_nav', args=('contact', ))),
#                         ACTION_CANCEL
#                     ]))
#             for lineid in utils.get_employees_lineid(patient.managers.filter(manager__relation="照護經理")):
#                 line_bot.push_message(lineid, template)

#     customer = utils.get_employee(event)
#     if customer:
#         for patient in customer.patients.all():
#             template = TemplateSendMessage(
#                 alt_text="家屬緊急通報",
#                 template=ButtonsTemplate(
#                     text="家屬緊急通報\n個案: %s\n時間 %s" % (patient.name, strftime, ),
#                     actions=[
#                         URITemplateAction("個案資訊及聯絡", settings.SITE_ROOT + reverse('line_nav', args=('contact', ))),
#                         ACTION_CANCEL
#                     ]))
#             for lineid in utils.get_employees_lineid(patient.managers.filter(manager__relation="照護經理")):
#                 line_bot.push_message(lineid, template)


# def dismiss_confirm(line_bot, event):
#     line_bot.reply_message(event.reply_token, TEMPLATE_DISMISS_CONFIRM)


# def dismiss(line_bot, event):
#     line_bot.reply_message(event.reply_token, TextSendMessage("緊急狀況解除"))


def handle_postback(line_bot, event, resp):
    stage, value = resp['stage'], resp.get('V')
    if stage == STAGE_INIGITION:
        select_patient(line_bot, event, value)
    # elif stage == STAGE_INIGITION_CONFIRM:
    #     confirm_emergency_action(line_bot, event, value)
    # elif stage == STAGE_SELECT_TARGET:
    #     update_emergency_action(line_bot, event, value)
    # elif stage == STAGE_TRANSFER_CONFIRM:
    #     transfer_confirm(line_bot, event, value)
    # elif stage == STAGE_TRANSFER:
    #     transfer(line_bot, event)
    # elif stage == STAGE_DISMISS_CONFIRM:
    #     dismiss_confirm(line_bot, event)
    # elif stage == STAGE_DISMISS:
    #     dismiss(line_bot, event)
