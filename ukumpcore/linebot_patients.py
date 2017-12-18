
from linebot.models import TemplateSendMessage, TextSendMessage, ButtonsTemplate, ConfirmTemplate, CarouselTemplate, CarouselColumn, PostbackTemplateAction, URITemplateAction

from django.utils.crypto import get_random_string
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
import json
import pytz

from ukumpcore.crm.agile import create_crm_ticket, get_patient_crm_url
from customer.models import Profile as Customer
from patient.models import Profile as Patient, CareDailyReport
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
            URITemplateAction('查閱詳情', settings.SITE_ROOT + reverse("patient_summary", args=(patient.pk, )) + "#%i" % i),
            PostbackTemplateAction('聯繫照護團隊', json.dumps({'T': T_PATIENT, 'stage': STAGE_CONTECT, 'V': (patient.id, i)}))
        )) for i, label in enumerate(CATALOGS)]
    return TemplateSendMessage(alt_text='%s 在 %s 的日報表已經可以查閱' % (patient.name, text_date),
                               template=CarouselTemplate(columns=columns))


def prepare_dairly_cards():
    ignore_count, sent_count, padding_count = 0, 0, 0

    date = timezone.now().astimezone(fix_tz).date()
    text_date = date.strftime('%Y-%m-%d')
    for patient in Patient.objects.filter(caredailyreport__report_date=date).exclude(caredailyreport__reviewed_by=None):
        if not patient.extend:
            patient.extend = {}

        if patient.extend.get('last_cart') == text_date:
            ignore_count += 1
            continue
        else:
            patient.extend['last_cart'] = text_date

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
                 'actions': [{'type': 'url', 'label': '查閱詳情', 'url': settings.SITE_ROOT + reverse("patient_summary", args=(patient.pk, )) + '#catalog-%i' % i},
                             {'type': 'postback', 'label': '聯繫照護團隊', 'data': json.dumps({'T': T_PATIENT, 'stage': STAGE_CONTECT, 'V': (patient.id, i)})}]}
                for i, label in enumerate(CATALOGS)]
        })

        sent_count += 1
        patient.save()

        for customer in patient.customers.all():
            customer.push_raw_message(message)

    for report in CareDailyReport.objects.filter(report_date=date, reviewed_by=None):
        padding_count += 1

        review_url = settings.SITE_ROOT + reverse('patient_daily_report', args=(report.patient_id, report.report_date, report.report_period))
        title = '%s 的日報正在等待審核 (重複通知)' % report.patient.name
        text = '日期 %s\n照服員 %s\n' % (report.report_date, report.filled_by.name)
        message = json.dumps({
            'M': 'buttons',
            'title': title,
            'alt': title,
            'text': text,
            'actions': ({'type': 'url', 'label': '審核', 'url': review_url}, )
        })
        for employee in report.patient.managers.filter(manager__relation="照護經理"):
            employee.push_raw_message(message)
    return ignore_count, sent_count, padding_count


def request_daily_reports(line_bot, event):
    result = utils.get_patients(event)
    count = sum(map(lambda x: x.patients.count(), result))

    if count > 1:
        columns = []

        if result.manager.patients:
            columns += utils.generate_patients_card(
                '照護經理 %s' % result.manager.owner.name, '請選擇最新日報個案',
                {'S': '', 'T': T_PATIENT, 'stage': STAGE_GET_CARD},
                result.manager.patients)
        if result.nurse.patients:
            columns += utils.generate_patients_card(
                '照護員 %s' % result.nurse.owner.name, '請選擇最新日報個案',
                {'S': '', 'T': T_PATIENT, 'stage': STAGE_GET_CARD},
                result.nurse.patients)
        if result.customer.patients:
            columns += utils.generate_patients_card(
                '家屬 %s' % result.customer.owner.name, '請選擇最新日報個案',
                {'S': '', 'T': T_PATIENT, 'stage': STAGE_GET_CARD},
                result.customer.patients)
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text='請選擇最新日報個案',
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
        # if 'phone' in manager.profile:
        #     actions.append(URITemplateAction('撥打行動電話', 'tel://%s' % manager.profile['phone']))
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


def handle_association(line_bot, event, resp):
    action, pid, cid = resp['value']

    customer = utils.get_customer(event)
    request_from = Customer.objects.get(id=cid)

    try:
        patient = customer.patients.get(guardian__master=True, id=pid)
        relation = cache.get('_line_asso_add:%i_%i' % (pid, cid))

        if relation:
            cache.delete('_line_asso_add:%i_%i' % (pid, cid))
            if action:
                patient.guardian_set.create(customer=request_from, relation=relation, master=False)
                for employee in patient.managers.filter(manager__relation='照護經理'):
                    employee.push_message('%s 已經授權家屬 %s 加入 %s 的照護群組' % (customer.name, request_from.name, patient.name))
                line_bot.reply_message(event.reply_token, TextSendMessage(
                    text='已經授權 %s 加入 %s 照護群組請求。' % (request_from.name, patient.name)))
            else:
                line_bot.reply_message(event.reply_token, TextSendMessage(
                    text='已經撤銷 %s 加入 %s 照護群組請求。' % (request_from.name, patient.name)))
        else:
            line_bot.reply_message(event.reply_token, TextSendMessage(
                text='授權群組請求已經過期或已經被撤銷，請家屬重新提出加入請求。'))
    except (Patient.DoesNotExist, Patient.MultipleObjectsReturned):
        line_bot.reply_message(event.reply_token, TextSendMessage(
            text='無權限執行此操作'))
