
from django.core.management.base import BaseCommand
from ukumpcore.crm.agile import sync_patients, sync_customers


class Command(BaseCommand):
    help = 'Sync Align CRM'

    def handle(self, *args, **options):
        print('Patient: %s records synced' % sync_patients())
        print('Customer: %s records synced' % sync_customers())
