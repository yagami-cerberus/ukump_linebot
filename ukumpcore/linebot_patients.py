
from linebot.models import TemplateSendMessage, TextSendMessage, ButtonsTemplate, CarouselTemplate, CarouselColumn, PostbackTemplateAction, URITemplateAction

from django.utils.crypto import get_random_string
from django.core.cache import cache
from django.utils import timezone  # , dateparse
from django.conf import settings
from django.urls import reverse
# from django.db import transaction
import json
import pytz

# from employee.models import Profile as Employee, LineMessageQueue as EmployeeLineMessageQueue
from patient.models import Profile as Patient
from . import linebot_utils as utils

CATALOGS = ("生理狀態", "精神狀態", "營養排泄", "活動狀態")
fix_tz = pytz.timezone('Etc/GMT-8')

T_CONTECT = "NCCONTECT"
T_PHONE = "NCCONTECT_PHONE"
T_NURSING = 'NURSING'
STAGE_GET_CARD = 'GC'


def generate_line_cards(patient, date):
    token = get_random_string(16)
    cache.set('_patient_card:%s' % token, json.dumps({'p': patient.id, 'd': date.strftime("%Y-%m-%d")}), 259200)
    imgurl_base = "https://76o5au1sya.execute-api.ap-northeast-1.amazonaws.com/staged/integrations/%%s/?token=%s" % token

    columns = [CarouselColumn(
        thumbnail_image_url=imgurl_base % i,
        text=label,
        actions=(
            URITemplateAction('查閱詳情', settings.SITE_ROOT + reverse("patient_summary", args=(patient.pk, i))),
            PostbackTemplateAction('聯繫照護經理', json.dumps({'T': T_CONTECT, 'p': patient.id, 'catalog': i}))
        )) for i, label in enumerate(CATALOGS)]
    return TemplateSendMessage(alt_text='日報表已經可以查閱', template=CarouselTemplate(columns=columns))


def prepare_dairly_cards():
    date = timezone.now().astimezone(fix_tz).date()
    for patient in Patient.objects.filter(caredailyreport__report_date=date).exclude(caredailyreport__reviewed_by=None):
        token = get_random_string(16)
        cache.set('_patient_card:%s' % token, json.dumps({'p': patient.id, 'd': date.strftime("%Y-%m-%d")}), 259200)
        imgurl_base = "https://76o5au1sya.execute-api.ap-northeast-1.amazonaws.com/staged/integrations/%%s/?token=%s" % token

        message = json.dumps({
            'M': 'c',
            'alt': '日報表已經可以查閱',
            'col': [
                {'url': imgurl_base % i,
                 'text': label,
                 'a': [('u', '查閱詳情', settings.SITE_ROOT + reverse("patient_summary", args=(patient.pk, i))),
                       ('p', '聯繫照護經理', json.dumps({'T': T_CONTECT, 'p': patient.id, 'catalog': i}))]}
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
                {'S': '', 'T': T_NURSING, 'stage': STAGE_GET_CARD},
                result.manager.patients)
        if result.nurse.patients:
            columns += utils.generate_patients_card(
                '照護員 %s' % result.nurse.owner.name, '請選擇個案',
                {'S': '', 'T': T_NURSING, 'stage': STAGE_GET_CARD},
                result.nurse.patients)
        if result.customer.patients:
            columns += utils.generate_patients_card(
                '家屬 %s' % result.customer.owner.name, '請選擇個案',
                {'S': '', 'T': T_NURSING, 'stage': STAGE_GET_CARD},
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
        line_bot.reply_message(event.reply_token, TextSendMessage(text="沒有可用的報告。"))


def contect_manager(line_bot, event, resp):
    patient = Patient.objects.filter(pk=resp['p']).get()
    catalog = CATALOGS[resp['catalog']]

    actions = []
    manager = patient.managers.filter(manager__relation="照護經理").first()
    if manager and manager.profile:
        if "line_link" in manager.profile:
            actions.append(URITemplateAction("透過LINE聯繫", manager.profile["line_link"]))
        if "phone" in manager.profile:
            actions.append(PostbackTemplateAction("撥打行動電話", json.dumps({"T": T_PHONE, "tel": manager.profile["phone"]})))
    actions.append(URITemplateAction("留言關懷中心", "https://www.ukump.com/"))

    template = TemplateSendMessage(
        alt_text="聯繫照護經理",
        template=ButtonsTemplate(
            text="聯繫照護經理關於 %s 之 %s" % (patient.name, catalog, ),
            actions=actions))
    line_bot.reply_message(event.reply_token, template)


def contect_phone(line_bot, event, resp):
    line_bot.reply_message(event.reply_token, TextSendMessage("聯絡電話 tel://%s" % resp["tel"]))


def handle_postback(line_bot, event, resp):
    stage, value = resp['stage'], resp.get('V')
    if stage == STAGE_GET_CARD:
        request_cards_with_patient(line_bot, event, value)
