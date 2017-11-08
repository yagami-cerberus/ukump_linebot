
from linebot.models import TemplateSendMessage, ButtonsTemplate, PostbackTemplateAction, URITemplateAction
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
import json

from linebot.models import TemplateSendMessage, TextSendMessage, CarouselTemplate
from patient.models import Profile as Patient

from . import nursing_scheduler
from . import linebot_utils as utils

T_REPORT = 'T_REPORT'

STAGE_INIGITION = 'i'
STAGE_LIST_DATE = 'd'


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
                    '照護經理 %s' % result.manager.owner.name, '請選擇案例',
                    {'S': '', 'T': T_REPORT, 'stage': STAGE_INIGITION, 'r': 'm'},
                    result.manager.patients, label=manager_patient_label)
            if result.nurse.patients:
                columns += utils.generate_patients_card(
                    '照護員 %s' % result.nurse.owner.name, '請選擇案例',
                    {'S': '', 'T': T_REPORT, 'stage': STAGE_INIGITION, 'r': 'n'},
                    result.nurse.patients)
            line_bot.reply_message(event.reply_token, TemplateSendMessage(
                alt_text="請選擇檔案檢視對象",
                template=CarouselTemplate(columns=columns)))
        elif count == 1:
            if result.manager.patients:
                select_patient(line_bot, event, patient=result.manager.patients.first(), role='m')
            elif result.nurse.patients:
                select_patient(line_bot, event, patient=result.nurse.patients.first(), role='n')
    elif result.customer.owner:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="無法取得可通報的照護對象，請直接與照護經理聯絡。"))
    else:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="請先註冊會員。"))


def select_patient(line_bot, event, value=None, patient=None, role=None):
    if not patient:
        patient = Patient.objects.get(pk=value)

    now = timezone.now().astimezone(nursing_scheduler.fix_tz)

    if role == 'm':
        actions = []

        for r in patient.caredailyreport_set.today():
            if r.report_period == 12:
                actions.append(
                    URITemplateAction('上午', settings.SITE_ROOT + \
                                             reverse('patient_daily_report', args=(patient.id, now.strftime('%Y-%m-%d'), 12))))
            elif r.report_period == 18:
                actions.append(
                    URITemplateAction('下午', settings.SITE_ROOT + \
                                             reverse('patient_daily_report', args=(patient.id, now.strftime('%Y-%m-%d'), 18))))
        actions.append(
                PostbackTemplateAction('其他日期', json.dumps({'S': '', 'T': T_REPORT, 'stage': STAGE_LIST_DATE, 'V': patient.id})))
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text='請選擇報表',
            template=ButtonsTemplate(title='%s 個案報告' % patient.name, text='請選擇報告', actions=actions)))

    elif role == 'n':
        t_noon = nursing_scheduler.create_datetime(now, nursing_scheduler.NOON)
        t_night = nursing_scheduler.create_datetime(now, nursing_scheduler.NIGHT)

        flags = 0
        for s in patient.nursing_schedule.today_schedule():
            if t_noon in s.schedule:
                flags |= 1
            if t_night in s.schedule:
                flags |= 2
        actions = []
        if flags & 1:
            actions.append(
                URITemplateAction('上午', settings.SITE_ROOT + \
                                         reverse('patient_daily_report', args=(patient.id, now.strftime('%Y-%m-%d'), 12))))
        if flags & 2:
            actions.append(
                URITemplateAction('下午', settings.SITE_ROOT + \
                                         reverse('patient_daily_report', args=(patient.id, now.strftime('%Y-%m-%d'), 18))))
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text='請選擇報表',
            template=ButtonsTemplate(title='%s 個案報告' % patient.name, text='請選擇報告', actions=actions)))
    else:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="params error"))


def handle_postback(line_bot, event, resp):
    stage, value = resp['stage'], resp.get('V')
    if stage == STAGE_INIGITION:
        select_patient(line_bot, event, value, role=resp.get('r'))
    elif stage == STAGE_LIST_DATE:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="not ready for use"))

