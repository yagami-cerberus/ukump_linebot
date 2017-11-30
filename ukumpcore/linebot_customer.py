
from linebot.models import (  # noqa
    TemplateSendMessage, URITemplateAction, ButtonsTemplate
)


def main_page(line_bot, event):
    line_bot.reply_message(event.reply_token, TemplateSendMessage(
        alt_text='請選擇功能',
        template=ButtonsTemplate(
            text='請選擇功能',
            actions=(
                URITemplateAction(label='最新活動', uri='http://lmgtfy.com/?q=%E7%94%B1%E5%BA%B7%E7%85%A7%E8%AD%B7+%E6%9C%80%E6%96%B0%E6%B4%BB%E5%8B%95'),
                URITemplateAction(label='本期促銷', uri='http://lmgtfy.com/?q=%E7%94%B1%E5%BA%B7%E7%85%A7%E8%AD%B7+%E6%9C%AC%E6%9C%9F%E4%BF%83%E9%8A%B7'),
                URITemplateAction(label='照護專欄', uri='http://lmgtfy.com/?q=%E7%94%B1%E5%BA%B7%E7%85%A7%E8%AD%B7+%E7%85%A7%E8%AD%B7%E5%B0%88%E6%AC%84')
            ))))
