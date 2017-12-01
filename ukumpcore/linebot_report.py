
from linebot.models import TemplateSendMessage, TextSendMessage, ButtonsTemplate, URITemplateAction, CarouselTemplate, PostbackTemplateAction
from django.utils import timezone
from django.conf import settings
from django.urls import reverse

from patient.models import Profile as Patient, CareDailyReport

from . import linebot_nursing
from . import linebot_utils as utils

T_REPORT = 'T_REPORT'

STAGE_INIGITION = 'i'
STAGE_REJECT = 'r'


def manager_patient_label(p):
    if p.caredailyreport_set.today().filter(reviewed_by=None):
        return '%s (有待審核報表)' % p.name
    else:
        return p.name


def ignition_report(line_bot, event):
    result = utils.get_patients(event)
    if result.manager.owner:
        count = sum(map(lambda x: x.patients.count(), result[:2]))

        if count > 1:
            columns = []

            if result.manager.patients:
                columns += utils.generate_patients_card(
                    '照護經理 %s' % result.manager.owner.name, '請選擇日報表檢視個案',
                    {'S': '', 'T': T_REPORT, 'stage': STAGE_INIGITION, 'r': 'm'},
                    result.manager.patients, label=manager_patient_label)
            if result.nurse.patients:
                columns += utils.generate_patients_card(
                    '照護員 %s' % result.nurse.owner.name, '請選擇日報表檢視個案',
                    {'S': '', 'T': T_REPORT, 'stage': STAGE_INIGITION, 'r': 'n'},
                    result.nurse.patients)
            line_bot.reply_message(event.reply_token, TemplateSendMessage(
                alt_text="請選擇日報表檢視對象",
                template=CarouselTemplate(columns=columns)))
        elif count == 1:
            if result.manager.patients:
                select_patient(line_bot, event, patient=result.manager.patients.first(), role='m')
            elif result.nurse.patients:
                select_patient(line_bot, event, patient=result.nurse.patients.first(), role='n')
        else:
            line_bot.reply_message(event.reply_token, TextSendMessage(text="沒有可用個案"))
    elif result.customer.owner:
        count = len(result.customer.patients)
        if count > 1:
            columns = utils.generate_patients_card(
                '家屬 %s' % result.customer.owner.name, '請選擇日報表檢視個案',
                {'S': '', 'T': T_REPORT, 'stage': STAGE_INIGITION, 'r': 'c'},
                result.nurse.patients)
            line_bot.reply_message(event.reply_token, TemplateSendMessage(
                alt_text="請選擇個案",
                template=CarouselTemplate(columns=columns)))
        elif count == 1:
            select_patient(line_bot, event, patient=result.nurse.patients.first(), role='c')
        else:
            line_bot.reply_message(event.reply_token, TextSendMessage(text="沒有可用個案"))
    else:
        raise utils.not_member_error


def select_patient(line_bot, event, value=None, patient=None, role=None):
    if not patient:
        patient = Patient.objects.get(pk=value)

    now = timezone.now().astimezone(linebot_nursing.fix_tz)
    str_now = now.strftime('%Y-%m-%d')

    if role == 'm':
        actions = []

        for r in patient.caredailyreport_set.today():
            form_name = settings.CARE_REPORTS.get(r.form_id, {}).get('label', '日報表')
            label = '%s (%s)' % (form_name, '已審核' if r.reviewed_by_id else '未審核')
            actions.append(
                URITemplateAction(label, settings.SITE_ROOT + reverse('patient_daily_report', args=(patient.id, str_now, 18))))
        actions.append(
            URITemplateAction('其他日期', settings.SITE_ROOT + reverse('patient_summary', args=(patient.id, ))))
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text='%s 日報表' % str_now,
            template=ButtonsTemplate(title='%s 個案日報表' % patient.name,
                                     text='日期：%s' % str_now, actions=actions)))

    elif role == 'n':
        report = CareDailyReport.get_report(patient.id, str_now, 18)
        if report:
            if report.reviewed_by_id:
                reply_message = TemplateSendMessage('本日報表已審核完畢無法編輯')
            else:
                form_name = settings.CARE_REPORTS.get(report.form_id, {}).get('label', '日報表')
                reply_message = TemplateSendMessage(
                    alt_text='%s 日報表' % str_now,
                    template=ButtonsTemplate(
                        title='%s 個案日報表' % patient.name, text='日期：%s' % str_now,
                        actions=(URITemplateAction('編輯 %s' % form_name,
                                                   settings.SITE_ROOT + reverse('patient_daily_report', args=(patient.id, str_now, 18))),)))
        else:
            form_id = CareDailyReport.get_form_id(patient.id, utils.get_employee_id(event), now)
            form_name = settings.CARE_REPORTS.get(form_id, {}).get('label', '日報表')
            reply_message = TemplateSendMessage(
                alt_text='%s 日報表' % str_now,
                template=ButtonsTemplate(
                    title='%s 個案日報表' % patient.name, text='日期：%s' % str_now,
                    actions=(URITemplateAction('填寫 %s' % form_name,
                                               settings.SITE_ROOT + reverse('patient_daily_report', args=(patient.id, str_now, 18))),)))

        line_bot.reply_message(event.reply_token, reply_message)

    elif role == 'c':
        actions = []
        meta = patient.extend if patient.extend else {}

        bill_url = meta.get('bill_url')
        payment_url = meta.get('payment_url')

        if bill_url and (bill_url.startswith('http://') or bill_url.startswith('https://')):
            actions.append(URITemplateAction('帳單查詢', bill_url))
        else:
            actions.append(PostbackTemplateAction('帳單查詢', {'T': T_REPORT, 'stage': STAGE_REJECT, 'V': '沒有帳單'}))

        if payment_url and (payment_url.startswith('http://') or payment_url.startswith('https://')):
            actions.append(URITemplateAction('線上繳費', payment_url))
        else:
            actions.append(PostbackTemplateAction('線上繳費', {'T': T_REPORT, 'stage': STAGE_REJECT, 'V': '沒有繳費資料'}))

        actions.append(URITemplateAction('客戶滿意度', 'https://www.google.com/'))

        try:
            line_bot.reply_message(event.reply_token, TemplateSendMessage(
                alt_text='%s 照護秘書' % str_now,
                template=ButtonsTemplate(
                    text='%s 照護秘書' % patient.name, actions=actions)))
        except Exception as err:
            print(str(err), repr(err), err, actions)

    else:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="params error"))


def reject(line_bot, event, value):
    line_bot.reply_message(event.reply_token, TextSendMessage(text=value))


def handle_postback(line_bot, event, resp):
    stage, value = resp['stage'], resp.get('V')
    if stage == STAGE_INIGITION:
        select_patient(line_bot, event, value, role=resp.get('r'))
    elif stage == STAGE_REJECT:
        reject(line_bot, event, value)
