
from linebot.models import TemplateSendMessage, TextSendMessage, ButtonsTemplate, ConfirmTemplate, CarouselTemplate, CarouselColumn, PostbackTemplateAction, URITemplateAction

from django.utils.crypto import get_random_string
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
import json
import pytz

from ukumpcore.crm.agile import create_crm_ticket, get_patient_crm_url
from patient.models import Profile as Patient
from . import linebot_utils as utils

CATALOGS = ("生理狀態", "精神狀態", "營養排泄", "活動狀態")
fix_tz = pytz.timezone('Etc/GMT-8')

T_PATIENT = 'NURSING'
STAGE_GET_CARD = 'GC'
STAGE_CONTECT = 'CC'
STAGE_REPORT = 'CR'
STAGE_SUBMIT = 'CS'

CONTECT_TICKET_TEMPLATE = """提問: %(reporter)s
個案: <a href="%(patient_url)s">%(case_name)s</a>
分類: %(catalog)s
問題: %(message)s"""

CONTECT_REPLY_EMPLOYEE_TEMPLATE = """個案 %(case_name)s 提問
分類: %(catalog)s
問題: %(message)s

CRM Ticket #%(ticket_id)s
%(ticket_url)s"""


def generate_line_cards(patient, date):
    token = get_random_string(16)
    text_date = date.strftime("%Y-%m-%d")
    cache.set('_patient_card:%s' % token, json.dumps({'p': patient.id, 'd': text_date}), 259200)
    imgurl_base = "https://76o5au1sya.execute-api.ap-northeast-1.amazonaws.com/staged/integrations/%%s/?token=%s" % token

    columns = [CarouselColumn(
        thumbnail_image_url=imgurl_base % i,
        title=label,
        text=text_date,
        actions=(
            URITemplateAction('查閱詳情', settings.SITE_ROOT + reverse("patient_summary", args=(patient.pk, i))),
            PostbackTemplateAction('聯繫照護團隊', json.dumps({'T': T_PATIENT, 'stage': STAGE_CONTECT, 'V': (patient.id, i)}))
        )) for i, label in enumerate(CATALOGS)]
    return TemplateSendMessage(alt_text='%s 在 %s 的日報表已經可以查閱' % (patient.name, text_date),
                               template=CarouselTemplate(columns=columns))


def prepare_dairly_cards():
    date = timezone.now().astimezone(fix_tz).date()
    text_date = date.strftime('%Y-%m-%d')
    for patient in Patient.objects.filter(caredailyreport__report_date=date).exclude(caredailyreport__reviewed_by=None):
        token = get_random_string(16)
        cache.set('_patient_card:%s' % token, json.dumps({'p': patient.id, 'd': date.strftime("%Y-%m-%d")}), 259200)
        imgurl_base = "https://76o5au1sya.execute-api.ap-northeast-1.amazonaws.com/staged/integrations/%%s/?token=%s" % token

        message = json.dumps({
            'M': 'carousel',
            'alt': '%s 在 %s 的日報表已經可以查閱' % (patient.name, text_date),
            'columns': [
                {'imgurl': imgurl_base % i,
                 'title': label,
                 'text': text_date,
                 'actions': [{'type': 'url', 'label': '查閱詳情', 'url': settings.SITE_ROOT + reverse("patient_summary", args=(patient.pk, i))},
                             {'type': 'postback', 'label': '聯繫照護團隊', 'data': json.dumps({'T': T_PATIENT, 'stage': STAGE_CONTECT, 'V': (patient.id, i)})}]}
                for i, label in enumerate(CATALOGS)]
        })
        for customer in patient.customers.all():
            customer.push_raw_message(message)


def request_cards(line_bot, event):
    result = utils.get_patients(event)
    count = sum(map(lambda x: x.patients.count(), result))

    if count > 1:
        columns = []

        if result.manager.patients:
            columns += utils.generate_patients_card(
                '照護經理 %s' % result.manager.owner.name, '請選擇個案',
                {'S': '', 'T': T_PATIENT, 'stage': STAGE_GET_CARD},
                result.manager.patients)
        if result.nurse.patients:
            columns += utils.generate_patients_card(
                '照護員 %s' % result.nurse.owner.name, '請選擇個案',
                {'S': '', 'T': T_PATIENT, 'stage': STAGE_GET_CARD},
                result.nurse.patients)
        if result.customer.patients:
            columns += utils.generate_patients_card(
                '家屬 %s' % result.customer.owner.name, '請選擇個案',
                {'S': '', 'T': T_PATIENT, 'stage': STAGE_GET_CARD},
                result.customer.patients)
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text="請選擇緊急通報對象",
            template=CarouselTemplate(columns=columns)))
    elif count == 1:
        for c in result:
            if c.patients:
                request_cards_with_patient(line_bot, event, patient=c.patients.first())
                return
    elif result.manager.owner:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="無法取得個案，請直接與照護經理聯絡。"))
    elif result.customer.owner:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="無法取得個案，請直接與照護經理聯絡。"))
    else:
        raise utils.not_member_error


def request_cards_with_patient(line_bot, event, value=None, patient=None):
    if not patient:
        patient = Patient.objects.get(pk=value)
    date = patient.caredailyreport_set.order_by("-report_date").values_list("report_date", flat=True).first()
    if date:
        line_bot.reply_message(event.reply_token, generate_line_cards(patient, date))
    else:
        line_bot.reply_message(event.reply_token, TextSendMessage(text='沒有可用的報告。'))


def contect_manager(line_bot, event, value):
    patient = Patient.objects.filter(pk=value[0]).get()
    catalog = CATALOGS[value[1]]

    actions = []
    manager = patient.managers.filter(manager__relation='照護經理').first()
    if manager and manager.profile:
        if 'line_link' in manager.profile:
            actions.append(URITemplateAction('透過LINE聯繫', manager.profile['line_link']))
        if 'phone' in manager.profile:
            actions.append(URITemplateAction('撥打行動電話', 'tel://%s' % manager.profile['phone']))
    actions.append(PostbackTemplateAction('留言關懷中心',
                                          json.dumps({'T': T_PATIENT, 'stage': STAGE_REPORT, 'V': value})))

    template = TemplateSendMessage(
        alt_text='聯繫照護經理',
        template=ButtonsTemplate(
            text='聯繫照護經理關於 %s 之 %s' % (patient.name, catalog, ),
            actions=actions))
    line_bot.reply_message(event.reply_token, template)


def begin_ticket(line_bot, event, value):
    # patient = Patient.objects.filter(pk=value[0]).get()
    # catalog = CATALOGS[value[1]]
    cache.set('_line:reply:%s' % event.source.user_id, {'T': T_PATIENT, 'V': value}, 500)
    line_bot.reply_message(event.reply_token, TextSendMessage(text='請輸入想詢問的問題...'))


def final_ticket(line_bot, event, message, data):
    patient_id, catalog_id = data['V']
    # patient = Patient.objects.filter(pk=data[0]).get()
    # catalog = CATALOGS[data[1]]

    text = '詢問問題內容：\n%s' % message
    line_bot.reply_message(event.reply_token, TemplateSendMessage(
        alt_text='請使用手機檢視問題',
        template=ConfirmTemplate(
            text=text[:160],
            actions=[
                PostbackTemplateAction('確定', json.dumps({'T': T_PATIENT, 'stage': STAGE_SUBMIT, 'V': (patient_id, catalog_id, message)})),
                PostbackTemplateAction('重填', json.dumps({'T': T_PATIENT, 'stage': STAGE_REPORT, 'V': (patient_id, catalog_id)}))
            ])
    ))


def submit_ticket(line_bot, event, value):
    source = utils.get_customer(event) or utils.get_employee(event)
    patient_id, catalog_id, message = value
    patient = Patient.objects.filter(pk=patient_id).get()
    catalog = CATALOGS[catalog_id]

    context = {
        'reporter': source.name,
        'message': message,
        'patient_url': get_patient_crm_url(patient),
        'case_name': patient.name,
        'catalog': catalog
    }
    ticket_id, ticket_url = create_crm_ticket(source, '關懷中心提問個案 %s' % patient.name, CONTECT_TICKET_TEMPLATE % context)
    context['ticket_id'] = ticket_id
    context['ticket_url'] = ticket_url
    for member in patient.managers.filter(manager__relation='照護經理'):
        member.push_message(CONTECT_REPLY_EMPLOYEE_TEMPLATE % context)

    line_bot.reply_message(
        event.reply_token,
        TextSendMessage(
            text='關懷中心案件編號 #%s\n\n照護經理與關懷中心已收到您針對 %s 所送出的問題，我們將儘速回覆。' % (ticket_id, patient.name)))


def handle_postback(line_bot, event, resp):
    stage, value = resp['stage'], resp.get('V')
    if stage == STAGE_GET_CARD:
        request_cards_with_patient(line_bot, event, value)
    elif stage == STAGE_CONTECT:
        contect_manager(line_bot, event, value)
    elif stage == STAGE_REPORT:
        begin_ticket(line_bot, event, value)
    elif stage == STAGE_SUBMIT:
        submit_ticket(line_bot, event, value)


def handle_message(line_bot, event, message, data):
    final_ticket(line_bot, event, message, data)
