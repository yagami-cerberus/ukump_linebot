
from django.utils.dateparse import parse_date
from django.utils import timezone
import json

from linebot.models import TemplateSendMessage, TextSendMessage, ButtonsTemplate, CarouselTemplate, PostbackTemplateAction
from patient.models import Profile as Patient
# from care.models import CourseDetail
from . import linebot_utils as utils

T_SIMPLE_QUERY = 'T_SQ'
STAGE_INIGITION = 'i'
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
            alt_text="請選擇個案",
            template=CarouselTemplate(columns=columns)))
    elif count == 1:
        for c in result:
            if c.patients:
                select_patient(line_bot, event, {'catalog': catalog}, patient=c.patients.first())
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
        date = parse_date(value['date']) if 'date' in value else timezone.localdate()
        ext = ('("weekly_mask" & %i > 0)' % (1 << date.isoweekday()), )
        courses = patient.course_schedule.extra(where=ext)
        # details = CourseDetail.objects.filter(table_id__in=courses.values_list('table_id', flat=True))

        title = '%s 在 %s 的課程' % (patient.name, date.strftime('%Y-%m-%d'))
        if courses:
            text = '\n'.join('\t%s' % c.table.name for c in courses)
        else:
            text = '沒有課程' % (patient.name, date.strftime('%Y-%m-%d'))
        # if details:
        #     text = '\n'.join('%s %s' % (d.scheduled_at.strftime('%H:%M'), d.name) for d in details)
        # else:
        #     text = '%s 在 %s 沒有課程' % (patient.name, date.strftime('%Y-%m-%d'))

        prev_date = (date + timezone.timedelta(days=-1)).strftime('%Y-%m-%d')
        next_date = (date + timezone.timedelta(days=1)).strftime('%Y-%m-%d')
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text=title,
            template=ButtonsTemplate(
                title=title[:40], text=text[:60],
                actions=[
                    PostbackTemplateAction(
                        '前一天 (%s)' % prev_date,
                        json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_INIGITION,
                                    'V': {'pid': patient.id, 'c': catalog, 'date': prev_date}})),
                    PostbackTemplateAction(
                        '後一天 (%s)' % next_date,
                        json.dumps({'T': T_SIMPLE_QUERY, 'stage': STAGE_INIGITION,
                                    'V': {'pid': patient.id, 'c': catalog, 'date': next_date}}))
                ]
            )
        ))

    elif catalog == CATALOG_CONTECT:
        lines = ['%s 的聯絡團隊' % patient.name]
        for m in patient.manager_set.all():
            lines.append('%s - %s' % (m.employee.name, m.relation))
        line_bot.reply_message(event.reply_token, TextSendMessage(text='\n'.join(lines)))


def handle_postback(line_bot, event, resp):
    stage, value = resp['stage'], resp.get('V')
    if stage == STAGE_INIGITION:
        select_patient(line_bot, event, value)
