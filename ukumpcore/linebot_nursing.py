
from django.utils.crypto import get_random_string
from django.core.cache import cache
from django.utils import timezone  # , dateparse
from django.conf import settings
from django.urls import reverse
# from django.db import transaction
from datetime import time  # , timedelta
import json
import pytz

from linebot.models import TemplateSendMessage, ButtonsTemplate, URITemplateAction, PostbackTemplateAction, TextSendMessage

from ukumpcore.linebot_utils import get_customer
from customer.models import LineMessageQueue as CustomerLineMessageQueue
# from employee.models import Profile as Employee, LineMessageQueue as EmployeeLineMessageQueue
from patient.models import Profile as Patient, NursingSchedule  # , CareHistory

CATALOGS = ("生理狀態", "精神狀態", "營養排泄", "活動狀態")
fix_tz = pytz.timezone('Etc/GMT-8')

NOON = time(12, 30)
NIGHT = time(18, 00)
T_NUSRING_BEGIN = "NCBEGIN"
T_CARE_QUESTION_POSTBACK = "NCQUESP"
T_CONTECT = "NCCONTECT"
T_PHONE = "NCCONTECT_PHONE"


def prepare_dairly_cards():
    today = timezone.now().astimezone(fix_tz).date()
    pid = NursingSchedule.objects.today_schedule().values_list('patient_id', flat=True)
    for patient in Patient.objects.filter(id__in=pid):
        prepare_dairly_card(patient, today)


def prepare_dairly_card(patient, date):
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
    for guardian in patient.guardian_set.all():
        CustomerLineMessageQueue(customer_id=guardian.customer_id, scheduled_at=timezone.now(),
                                 message=message).save()


def request_cards(line_bot, event):
    customer = get_customer(event)
    for patient in customer.patients.all():
        date = patient.caredailyreport_set.order_by("-report_date").values_list("report_date", flat=True).first()
        if date:
            prepare_dairly_card(patient, date)


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
