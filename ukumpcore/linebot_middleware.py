
from django.conf import settings
import traceback
import sys

from linebot.models import TextSendMessage
from ukumpcore.linebot_handler import line_bot


class LinebotMiddleware(object):
    admin_lineid = None

    def __init__(self, get_response):
        if hasattr(settings, 'LINEBOT_ADMIN'):
            self.admin_lineid = settings.LINEBOT_ADMIN

        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if self.admin_lineid:
            try:
                err_message = '%s\n==============\n%s' % (
                    exception,
                    ''.join(traceback.format_exception(*sys.exc_info())))
                line_bot.push_message(self.admin_lineid, TextSendMessage(err_message))
            except Exception:
                pass
