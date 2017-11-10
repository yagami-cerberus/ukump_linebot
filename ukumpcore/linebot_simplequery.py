
from django.utils import timezone

from linebot.models import TemplateSendMessage, TextSendMessage, ButtonsTemplate, CarouselTemplate, PostbackTemplateAction, URITemplateAction  # noqa
from patient.models import Profile as Patient
from care.models import CourseDetail
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
                {'S': '', 'T': T_SIMPLE_QUERY, 'stage': STAGE_INIGITION, 'catalog': catalog},
                result.manager.patients)
        if result.nurse.patients:
            columns += utils.generate_patients_card(
                '照護員 %s' % result.nurse.owner.name, '請選擇個案',
                {'S': '', 'T': T_SIMPLE_QUERY, 'stage': STAGE_INIGITION, 'catalog': catalog},
                result.nurse.patients)
        if result.customer.patients:
            columns += utils.generate_patients_card(
                '家屬 %s' % result.customer.owner.name, '請選擇個案',
                {'S': '', 'T': T_SIMPLE_QUERY, 'stage': STAGE_INIGITION, 'catalog': catalog},
                result.customer.patients)
        line_bot.reply_message(event.reply_token, TemplateSendMessage(
            alt_text="請選擇個案",
            template=CarouselTemplate(columns=columns)))
    elif count == 1:
        for c in result:
            if c.patients:
                select_patient(line_bot, event, patient=c.patients.first(), catalog=catalog)
                return
    elif result.manager.owner:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="無法取得個案清單，請直接與照護經理聯絡。"))
    elif result.customer.owner:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="無法取得個案清單，請直接與照護經理聯絡。"))
    else:
        line_bot.reply_message(event.reply_token, TextSendMessage(text="請先註冊會員。"))


def select_patient(line_bot, event, value=None, patient=None, catalog=None):
    if not patient:
        patient = Patient.objects.get(pk=value)

    if catalog == CATALOG_COURSE:
        ext = ('("weekly_mask" & %i > 0)' % (1 << timezone.localdate().isoweekday()), )
        courses = patient.course_schedule.extra(where=ext)
        details = CourseDetail.objects.filter(table_id__in=courses.values_list('table_id', flat=True))
        if details:
            lines = ['%s 的本日課程' % patient.name, '--------------']
            for d in details:
                lines.append('%s %s' % (d.scheduled_at.strftime('%H:%M'), d.name))
            line_bot.reply_message(event.reply_token, TextSendMessage(text='\n'.join(lines)))
        else:
            line_bot.reply_message(event.reply_token, TextSendMessage(text='%s 本日沒有課程' % patient.name))

    elif catalog == CATALOG_CONTECT:
        lines = ['%s 的聯絡團隊' % patient.name]
        for m in patient.manager_set.all():
            lines.append('%s - %s' % (m.employee.name, m.relation))
        line_bot.reply_message(event.reply_token, TextSendMessage(text='\n'.join(lines)))


def handle_postback(line_bot, event, resp):
    stage, value = resp['stage'], resp.get('V')
    if stage == STAGE_INIGITION:
        select_patient(line_bot, event, value, catalog=resp.get('catalog'))
