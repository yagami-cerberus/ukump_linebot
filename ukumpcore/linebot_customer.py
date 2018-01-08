
from django.utils.crypto import get_random_string
from django.core.cache import cache
from django.conf import settings
from django.urls import reverse
import json

from linebot.models import (  # noqa
    TemplateSendMessage, URITemplateAction, ButtonsTemplate, CarouselTemplate, PostbackTemplateAction, TextSendMessage
)
from patient.models import Profile as Patient
from . import linebot_utils as utils


T_CUSTOMER = 'customer'
STAGE_SELECT_CASE = 's'
STAGE_EXCHANGE = 'e'
STAGE_GEN_CODE = 'g'
STAGE_TOGGLE = 't'


def main_page(line_bot, event):
    actions = [
        URITemplateAction(label='最新活動', uri='http://lmgtfy.com/?q=%E7%94%B1%E5%BA%B7%E7%85%A7%E8%AD%B7+%E6%9C%80%E6%96%B0%E6%B4%BB%E5%8B%95'),
        URITemplateAction(label='本期促銷', uri='http://lmgtfy.com/?q=%E7%94%B1%E5%BA%B7%E7%85%A7%E8%AD%B7+%E6%9C%AC%E6%9C%9F%E4%BF%83%E9%8A%B7'),
        URITemplateAction(label='照護專欄', uri='http://lmgtfy.com/?q=%E7%94%B1%E5%BA%B7%E7%85%A7%E8%AD%B7+%E7%85%A7%E8%AD%B7%E5%B0%88%E6%AC%84')
    ]

    result = utils.get_patients(event)

    if not result.manager.owner and not result.customer.owner:
        actions.append(URITemplateAction('註冊',
                                         settings.SITE_ROOT + reverse('line_association')))

    elif result.manager.owner and result.manager.patients:
        actions.append(PostbackTemplateAction(
            label='產生邀請碼', data=json.dumps({'T': T_CUSTOMER, 'stage': STAGE_SELECT_CASE})))

    elif result.customer.patients:
        if result.customer.owner.guardian_set.filter(subscribe=True).count():
            actions.append(PostbackTemplateAction(
                label='取消訂閱', data=json.dumps({'T': T_CUSTOMER, 'stage': STAGE_TOGGLE, 'V': False})))
        else:
            actions.append(PostbackTemplateAction(
                label='訂閱', data=json.dumps({'T': T_CUSTOMER, 'stage': STAGE_TOGGLE, 'V': True})))

    try:
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text="請選擇功能",
            template=ButtonsTemplate(text='請選擇功能', actions=actions[:4])))
    except Exception as err:
        print(actions)
        print(err, repr(err))


def select_patient(line_bot, event, value):
    employee = utils.get_employee(event)
    patients = employee.patients.filter(manager__relation='照護經理')
    columns = utils.generate_patients_card(
        '照護經理 %s' % employee.name, '請選擇個案',
        {'T': T_CUSTOMER, 'stage': STAGE_GEN_CODE}, patients)
    line_bot.reply_message(event.reply_token, TemplateSendMessage(
        alt_text="請選擇個案",
        template=CarouselTemplate(columns=columns)))


def gen_code(line_bot, event, patient_id):
    patient = Patient.objects.get(id=patient_id)
    validate_code = get_random_string(6, allowed_chars='1234567890')
    cache.set('_line_asso_invcode:%s' % validate_code, patient_id, 600)

    line_bot.reply_message(event.reply_token, TemplateSendMessage(
        alt_text="已產生邀請碼",
        template=ButtonsTemplate(text='個案 %s 邀請碼：\n%s\n\n邀請碼10分鐘內有效' % (patient.name, validate_code),
                                 actions=(PostbackTemplateAction('轉送給客戶', json.dumps({'T': T_CUSTOMER, 'stage': STAGE_EXCHANGE, 'V': (patient_id, validate_code)})),))))


def exchange_code(line_bot, event, value):
    patient_id, validate_code = value
    patient = Patient.objects.get(id=patient_id)

    customers = patient.customers.filter(guardian__master=True)
    if customers:
        for customer in customers:
            customer.push_message('個案 %s 邀請碼：\n%s' % (patient.name, validate_code))
        line_bot.reply_message(event.reply_token, TextSendMessage('已將邀請碼轉送給客戶。'))
    else:
        line_bot.reply_message(event.reply_token, TextSendMessage('沒有客戶可以傳送。'))


def subscribe(line_bot, event, value):
    customer = utils.get_customer(event)
    customer.guardian_set.update(subscribe=value)

    line_bot.reply_message(event.reply_token, TextSendMessage(
        '完成訂閱' if value else '已取消訂閱'))


def handle_postback(line_bot, event, resp):
    stage, value = resp['stage'], resp.get('V')
    if stage == STAGE_SELECT_CASE:
        select_patient(line_bot, event, value)
    elif stage == STAGE_GEN_CODE:
        gen_code(line_bot, event, value)
    elif stage == STAGE_EXCHANGE:
        exchange_code(line_bot, event, value)
    elif stage == STAGE_TOGGLE:
        subscribe(line_bot, event, value)
