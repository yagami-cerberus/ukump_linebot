
from django.core.management.base import BaseCommand
from ukumpcore.crm.agile import sync_patients, sync_customers


class Command(BaseCommand):
    help = 'Sync Align CRM'

    def handle(self, *args, **options):
        sync_patients()
        sync_customers()
