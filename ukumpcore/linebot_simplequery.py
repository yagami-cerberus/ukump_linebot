
from django.utils.dateparse import parse_date
from django.utils.crypto import get_random_string
from django.core.cache import cache
from django.utils import timezone
import json

from linebot.models import (
    TemplateSendMessage, TextSendMessage, ButtonsTemplate, CarouselTemplate, ConfirmTemplate,
    PostbackTemplateAction)
from employee.models import Profile as Employee
from patient.models import Profile as Patient, DummyNote
from care.models import CourseDetail
from . import linebot_utils as utils

T_SIMPLE_QUERY = 'T_SQ'
STAGE_INIGITION = 'i'
STAGE_FETCH_COURSE = 'fc'
STAGE_READ_NOTE = 'rn'
STAGE_WRITE_NOTE = 'wn'
STAGE_COMMIT_NOTE = 'cn'
STAGE_CLEAN_NOTE = 'dn'
STAGE_CLEAN_CONFIRM_NOTE = 'cdn'

STAGE_RETURN_CONTEXT = 'r'
STAGE_SEND_NOTE = 'sn'
STAGE_PASS_NOTE = 'pn'
CATALOG_COURSE = 'course'
CATALOG_CONTECT = 'contect'


def ignition(line_bot, event, catalog):
    result = utils.get_patients(event)

    count = sum(map(lambda x: x.patients.count(), result))

    if count > 1:
        columns = []

        if result.manager.patients:
            columns += utils.generate_patients_card(
                '照護經理 %s' % result.manager.owner.name, '請選擇個案',
                {'T': T_SIMPLE_QUERY, 'stage': STAGE_INIGITION},
                result.manager.patients,
                value=lambda p: {'pid': p.id, 'c': catalog})
        if result.nurse.patients:
            columns += utils.generate_patients_card(
                '照護員 %s' % result.nurse.owner.name, '請選擇個案',
                {'T': T_SIMPLE_QUERY, 'stage': STAGE_INIGITION},
                result.nurse.patients,
                value=lambda p: {'pid': p.id, 'c': catalog})
        if result.customer.patients:
            columns += utils.generate_patients_card(
                '家屬 %s' % result.customer.owner.name, '請選擇個案',
                {'T': T_SIMPLE_QUERY, 'stage': STAGE_INIGITION},
                result.customer.patients,
                value=lambda p: {'pid': p.id, 'c': catalog})
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text='請選擇個案',
            template=CarouselTemplate(columns=columns)))
    elif count == 1:
        for c in result:
            if c.patients:
                select_patient(line_bot, event, {'c': catalog}, patient=c.patients.first())
                return
    elif result.manager.owner:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="無法取得個案清單，請直接與照護經理聯絡。"))
    elif result.customer.owner:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="無法取得個案清單，請直接與照護經理聯絡。"))
    else:
        raise utils.not_member_error


def select_patient(line_bot, event, value, patient=None):
    if not patient:
        patient = Patient.objects.get(pk=value['pid'])
    catalog = value.get('c')

    if catalog == CATALOG_COURSE:
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text='請選擇功能',
            template=ButtonsTemplate(
                text='請選擇功能',
                actions=(
                    PostbackTemplateAction('課程表',
                                           json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_FETCH_COURSE,
                                                       'V': {'pid': patient.id, 'date': timezone.localdate().strftime('%Y-%m-%d')}})),
                    PostbackTemplateAction('讀取留言',
                                           json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_READ_NOTE,
                                                       'V': patient.id})),
                    PostbackTemplateAction('寫下留言',
                                           json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_WRITE_NOTE,
                                                       'V': (patient.id, None)})),
                    PostbackTemplateAction('清除留言',
                                           json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_CLEAN_NOTE,
                                                       'V': patient.id})),
                ))))

    elif catalog == CATALOG_CONTECT:
        text = '%s 的聯絡團隊' % patient.name
        actions = []
        manager = patient.managers.filter(manager__relation='照護經理').first()

        if manager and manager.profile and 'phone' in manager.profile:
            name, phone = manager.name, manager.profile['phone']
            actions.append(
                PostbackTemplateAction(
                    '照護經理 %s' % name,
                    json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_RETURN_CONTEXT,
                                'V': '照護經理 %s\n聯絡電話 %s' % (name, phone)})))

        for text_temp, queryset in (('照服員 %s (今日)', patient.nursing_schedule.today()),
                                    ('照服員 %s (明日)', patient.nursing_schedule.tomorrow())):
            for schedule in queryset:
                actions.append(
                    PostbackTemplateAction(
                        text_temp % name,
                        json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_SEND_NOTE,
                                    'V': (schedule.employee.id, patient.id, None)})))

        if actions:
            line_bot.reply_message(event.reply_token, TemplateSendMessage(
                alt_text=text,
                template=ButtonsTemplate(text=text, actions=actions[:4])))
        else:
            line_bot.reply_message(event.reply_token, TextSendMessage('無法取得 %s 的照護團隊資料' % patient.name))


class SharedNote(object):
    @classmethod
    def read(cls, line_bot, event, value):
        patient = Patient.objects.get(pk=value)

        text = []
        tsize = 0
        for dn in patient.dummynote_set.order_by('-created_at').iterator():
            t = dn.created_at.astimezone(timezone.get_current_timezone())
            lt = '%s 在 %s\n%s' % (dn.name, t.strftime('%Y-%m-%d %H點%M分'), dn.message)
            tsize += len(lt) + 20
            text.append(lt)
            if tsize > 300:
                break

        if text:
            text.reverse()
            line_bot.reply_message(event.reply_token, TextSendMessage(text='\n==========\n'.join(text)))
        else:
            line_bot.reply_message(event.reply_token, TextSendMessage(text='沒有留言'))

    @classmethod
    def write(cls, line_bot, event, value):
        patient_id, token = value
        if token:
            key = '_line:temp:%s:%s' % (event.source.user_id, token)
            if key in cache:
                cache.delete(key)
            else:
                line_bot.reply_message(event.reply_token, TextSendMessage('操作無效'))
                return

        cache.set('_line:reply:%s' % event.source.user_id, {'T': T_SIMPLE_QUERY, 'stage': STAGE_WRITE_NOTE, 'V': patient_id}, 500)
        line_bot.reply_message(event.reply_token, TextSendMessage(text='請輸入留言'))

    @classmethod
    def confirm(cls, line_bot, event, message, data):
        patient_id = data['V']
        text = '留言內容：\n%s' % message

        token = get_random_string(8)
        cache.set('_line:temp:%s:%s' % (event.source.user_id, token), (patient_id, message), 3600)
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text='請使用手機檢視內容',
            template=ConfirmTemplate(
                text=text[:160],
                actions=[
                    PostbackTemplateAction('確定', json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_COMMIT_NOTE, 'V': token})),
                    PostbackTemplateAction('重填', json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_WRITE_NOTE, 'V': (patient_id, token)}))
                ])
        ))

    @classmethod
    def commit(cls, line_bot, event, token):
        key = '_line:temp:%s:%s' % (event.source.user_id, token)
        value = cache.get(key)
        cache.delete(key)
        if value:
            patient_id, message = value
            source = utils.get_employee(event) or utils.get_customer(event)
            if source:
                DummyNote(name=source.name, patient_id=patient_id, message=message).save()
                line_bot.reply_message(event.reply_token, TextSendMessage('訊息已儲存'))
            else:
                line_bot.reply_message(event.reply_token, TextSendMessage('404'))
        else:
            line_bot.reply_message(event.reply_token, TextSendMessage('操作無效'))

    @classmethod
    def clean(cls, line_bot, event, value):
        pass

    @classmethod
    def clean_confirm(cls, line_bot, event, value):
        pass


def return_course(line_bot, event, value=None, patient=None, date=None):
    if not patient:
        patient = Patient.objects.get(pk=value['pid'])
    if not date:
        date = parse_date(value['date'])
    ext = ('("weekly_mask" & %i > 0)' % (1 << date.isoweekday()), )
    courses = patient.course_schedule.extra(where=ext)
    details = CourseDetail.objects.filter(table_id__in=courses.values_list('table_id', flat=True))

    title = '%s 在 %s 的課程' % (patient.name, date.strftime('%Y-%m-%d'))
    if details:
        text = '\n'.join('%s %s' % (d.scheduled_at.strftime('%H:%M'), d.name) for d in details)
    else:
        text = '%s 在 %s 沒有課程' % (patient.name, date.strftime('%Y-%m-%d'))

    prev_date = (date + timezone.timedelta(days=-1)).strftime('%Y-%m-%d')
    next_date = (date + timezone.timedelta(days=1)).strftime('%Y-%m-%d')
    line_bot.reply_message(event.reply_token, TemplateSendMessage(
        alt_text=title,
        template=ButtonsTemplate(
            text=(title + '\n\n' + text)[:160],
            actions=[
                PostbackTemplateAction(
                    '前一天 (%s)' % prev_date,
                    json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_FETCH_COURSE,
                                'V': {'pid': patient.id, 'date': prev_date}})),
                PostbackTemplateAction(
                    '後一天 (%s)' % next_date,
                    json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_FETCH_COURSE,
                                'V': {'pid': patient.id, 'date': next_date}}))
            ]
        )
    ))


def return_context(line_bot, event, value):
    line_bot.reply_message(event.reply_token, TextSendMessage(text=value))


class NursingNote(object):
    @classmethod
    def write(cls, line_bot, event, value):
        employee_id, patient_id, token = value
        if token:
            key = '_line:temp:%s:%s' % (event.source.user_id, token)
            if key in cache:
                cache.delete(key)
            else:
                line_bot.reply_message(event.reply_token, TextSendMessage('操作無效'))
                return

        cache.set('_line:reply:%s' % event.source.user_id, {'T': T_SIMPLE_QUERY, 'stage': STAGE_SEND_NOTE, 'V': (employee_id, patient_id)}, 500)
        line_bot.reply_message(event.reply_token, TextSendMessage(text='請輸入留言'))

    @classmethod
    def confirm(cls, line_bot, event, message, data):
        employee_id, patient_id = data['V']
        patient = Patient.objects.get(pk=patient_id)

        text = '留言內容：\n%s' % message
        pass_context = '收到針對個案 %s 的留言訊息\n%s' % (patient.name, message)

        token = get_random_string(8)
        cache.set('_line:temp:%s:%s' % (event.source.user_id, token), (employee_id, pass_context), 3600)

        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text='請使用手機檢視內容',
            template=ConfirmTemplate(
                text=text[:160],
                actions=[
                    PostbackTemplateAction('確定', json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_PASS_NOTE, 'V': token})),
                    PostbackTemplateAction('重填', json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_SEND_NOTE, 'V': (employee_id, patient_id, token)}))
                ])
        ))

    @classmethod
    def send(cls, line_bot, event, token):
        key = '_line:temp:%s:%s' % (event.source.user_id, token)
        value = cache.get(key)
        cache.delete(key)
        if value:
            employee_id, message = value
            Employee.objects.get(pk=employee_id).push_message(message)
            line_bot.reply_message(event.reply_token, TextSendMessage(text='已經將訊息轉送給照服員。'))
        else:
            line_bot.reply_message(event.reply_token, TextSendMessage('操作無效'))


def handle_postback(line_bot, event, resp):
    stage, value = resp['stage'], resp.get('V')
    if stage == STAGE_INIGITION:
        select_patient(line_bot, event, value)
    elif stage == STAGE_FETCH_COURSE:
        return_course(line_bot, event, value)
    elif stage == STAGE_READ_NOTE:
        SharedNote.read(line_bot, event, value)
    elif stage == STAGE_WRITE_NOTE:
        SharedNote.write(line_bot, event, value)
    elif stage == STAGE_COMMIT_NOTE:
        SharedNote.commit(line_bot, event, value)
    elif stage == STAGE_CLEAN_NOTE:
        SharedNote.clean(line_bot, event, value)
    elif stage == STAGE_CLEAN_CONFIRM_NOTE:
        SharedNote.clean_confirm(line_bot, event, value)
    elif stage == STAGE_RETURN_CONTEXT:
        return_context(line_bot, event, value)
    elif stage == STAGE_SEND_NOTE:
        NursingNote.write(line_bot, event, value)
    elif stage == STAGE_PASS_NOTE:
        NursingNote.send(line_bot, event, value)


def handle_message(line_bot, event, message, data):
    if data['stage'] == STAGE_SEND_NOTE:
        NursingNote.confirm(line_bot, event, message, data)
    elif data['stage'] == STAGE_WRITE_NOTE:
        SharedNote.confirm(line_bot, event, message, data)
