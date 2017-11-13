
from linebot.models import TemplateSendMessage, TextSendMessage, ButtonsTemplate, CarouselTemplate, PostbackTemplateAction
# from django.core.cache import cache
from ukumpcore.crm.agile import create_crm_ticket, get_patient_crm_url
from django.utils import timezone
import json

from patient.models import Profile as Patient
from . import linebot_utils as utils

T_EMERGENCY = 'T_EMERGENCY'

STAGE_INIGITION = 'i'
STAGE_SELECT_EVENT = 'e'
STAGE_SELECT_ACTION = 'a'
STAGE_COMMIT = 'c'
STAGE_SUBMIT = 's'

EMERGENCY_TICKET_TEMPLATE = """通報人: %(reporter)s
個案: <a href="%(patient_url)s">%(case_name)s</a>
聯絡電話: %(phone)s
緊急事項: %(event)s
處置: %(actions)s"""

EMERGENCY_REPLY_EMPLOYEE_TEMPLATE = """個案 %(case_name)s 緊急通報！
通報人: %(reporter)s
通報聯絡電話: %(phone)s
緊急事項: %(event)s
處置: %(actions)s

CRM Ticket #%(ticket_id)s
%(ticket_url)s"""


def format_message(value):
    t = timezone.datetime.fromtimestamp(value['t'])
    message = (
        '通報日期 %s' % t.strftime('%Y-%m-%d %H時%M分'),
        '事件：%s' % value.get('e', '未描述'),
        '處置：%s' % (', '.join(value['a']) if value.get('a') else '無')
    )
    return '\n'.join(message)


def ignition_emergency(line_bot, event):
    result = utils.get_patients(event)

    count = sum(map(lambda x: x.patients.count(), result))

    if count > 1:
        columns = []

        if result.manager.patients:
            columns += utils.generate_patients_card(
                '照護經理 %s' % result.manager.owner.name, '請選擇案例',
                {'S': '', 'T': T_EMERGENCY, 'stage': STAGE_INIGITION},
                result.manager.patients,
                value=lambda p: {'pid': p.id})
        if result.nurse.patients:
            columns += utils.generate_patients_card(
                '照護員 %s' % result.nurse.owner.name, '請選擇案例',
                {'S': '', 'T': T_EMERGENCY, 'stage': STAGE_INIGITION},
                result.nurse.patients,
                value=lambda p: {'pid': p.id})
        if result.customer.patients:
            columns += utils.generate_patients_card(
                '家屬 %s' % result.customer.owner.name, '請選擇案例',
                {'S': '', 'T': T_EMERGENCY, 'stage': STAGE_INIGITION},
                result.customer.patients,
                value=lambda p: {'pid': p.id})
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text='請選擇緊急通報對象',
            template=CarouselTemplate(columns=columns)))
    elif count == 1:
        for c in result:
            if c.patients:
                emergency_main_menu(line_bot, event, patient=c.patients.first())
                return
    elif result.manager.owner:
        line_bot.reply_message(event.reply_token, TextSendMessage(text='無法取得可通報的照護對象，請直接與照護經理聯絡。'))
    elif result.customer.owner:
        line_bot.reply_message(event.reply_token, TextSendMessage(text='無法取得可通報的照護對象，請直接與照護經理聯絡。'))
    else:
        raise utils.not_member_error


def emergency_main_menu(line_bot, event, value=None, patient=None):
    if patient:
        value = {'pid': patient.id, 't': timezone.now().timestamp(), 'a': []}
    else:
        patient = Patient.objects.get(pk=value['pid'])
        if 't' not in value:
            value['t'] = timezone.now().timestamp()
            value['a'] = []

    line_bot.reply_message(event.reply_token, TemplateSendMessage(
        alt_text='緊急通報',
        template=ButtonsTemplate(
            title='個案 %s 緊急通報' % patient.name,
            text=format_message(value),
            actions=[
                PostbackTemplateAction('選擇通報事件', json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_SELECT_EVENT, 'V': value})),
                PostbackTemplateAction('選擇處置內容', json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_SELECT_ACTION, 'V': value})),
                PostbackTemplateAction('送出緊急通報', json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_COMMIT, 'V': value}))
            ])
    ))


def select_event(line_bot, event, value):
    events = ('跌倒/受傷', '昏迷', '其他')

    def update_value(value, event):
        value = value.copy()
        value['e'] = event
        return value

    actions = [
        PostbackTemplateAction(e, json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_INIGITION, 'V': update_value(value, e)}))
        for e in events]

    patient = Patient.objects.get(pk=value['pid'])
    line_bot.reply_message(event.reply_token, TemplateSendMessage(
        alt_text='緊急通報',
        template=ButtonsTemplate(
            title='個案 %s 緊急通報' % patient.name,
            text=format_message(value),
            actions=actions)))


def select_action(line_bot, event, value):
    ACTIONS = ('已聯絡救護車(119)', '已聯絡警察(110)', '已自行送醫')  # noqa

    def build_action(value, action):
        value = value.copy()
        actions = value['a'].copy()

        if action in actions:
            actions.remove(action)
            value['a'] = actions
            return PostbackTemplateAction(
                '移除 "%s"' % action,
                json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_INIGITION, 'V': value}))
        else:
            actions.append(action)
            value['a'] = actions
            return PostbackTemplateAction(
                action,
                json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_INIGITION, 'V': value}))

    patient = Patient.objects.get(pk=value['pid'])
    line_bot.reply_message(event.reply_token, TemplateSendMessage(
        alt_text='緊急通報',
        template=ButtonsTemplate(
            title='個案 %s 緊急通報' % patient.name,
            text=format_message(value),
            actions=tuple(build_action(value, h) for h in ACTIONS))))


def commit(line_bot, event, value, timeout=False):
    value['t'] = timezone.now().timestamp()

    patient = Patient.objects.get(pk=value['pid'])
    message = format_message(value)

    if timeout:
        message = '此通報已經閒置過久，請重新點選提交送出\n %s' % message

    line_bot.reply_message(event.reply_token, TemplateSendMessage(
        alt_text='緊急通報',
        template=ButtonsTemplate(
            title='確認提交個案 %s 緊急通報' % patient.name,
            text=message,
            actions=[
                PostbackTemplateAction('確認提交送出', json.dumps({'S': '', 'T': T_EMERGENCY, 'stage': STAGE_SUBMIT, 'V': value}))
            ])
    ))


def submit(line_bot, event, value):
    if timezone.now().timestamp() - value['t'] > 180:
        commit(line_bot, event, value, timeout=True)
    else:
        source = utils.get_employee(event)
        if not source:
            source = utils.get_customer(event)

        patient = Patient.objects.get(pk=value['pid'])
        title = 'LINE 緊急通報案例 %s' % patient.name
        context = {
            'case_name': patient.name,
            'reporter': source.name,
            'phone': source.profile.get('phone') if source.profile else '',
            'event': value.get('e'),
            'actions': ', '.join(value.get('a')),
            'patient_url': get_patient_crm_url(patient)
        }

        ticket_id, ticket_url = create_crm_ticket(source, title, EMERGENCY_TICKET_TEMPLATE % context, emergency=True)

        context['ticket_id'] = ticket_id
        context['ticket_url'] = ticket_url
        for member in patient.managers.filter(manager__relation='照護經理'):
            member.push_message(EMERGENCY_REPLY_EMPLOYEE_TEMPLATE % context)

        line_bot.reply_message(
            event.reply_token,
            TextSendMessage(
                text='緊急通報案件編號 #%s\n\n照護經理與關懷中心已收到您針對 %s 所送出的緊急通報，必要時請直接聯繫照護經理。' % (ticket_id, patient.name)))


def handle_postback(line_bot, event, resp):
    stage, value = resp['stage'], resp.get('V')
    if stage == STAGE_INIGITION:
        emergency_main_menu(line_bot, event, value)
    elif stage == STAGE_SELECT_EVENT:
        select_event(line_bot, event, value)
    elif stage == STAGE_SELECT_ACTION:
        select_action(line_bot, event, value)
    elif stage == STAGE_COMMIT:
        commit(line_bot, event, value)
    else:
        submit(line_bot, event, value)
