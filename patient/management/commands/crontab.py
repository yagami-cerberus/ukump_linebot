from django.core.management.base import BaseCommand
from ukumpcore.linebot_handler import flush_messages_queue
from ukumpcore import linebot_nursing


class Command(BaseCommand):
    help = 'Scheduler'

    def handle(self, *args, **options):
        linebot_nursing.schedule_fixed_schedule_message()
        flush_messages_queue()
