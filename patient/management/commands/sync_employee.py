
from django.core.management.base import BaseCommand
from ukumpcore.crm.agile import get_employees_from_crm_document, update_employee_from_from_csv


class Command(BaseCommand):
    help = 'Sync employee from CRM document'

    def handle(self, *args, **options):
        created, updated_from_hr_id, updated_from_email = 0, 0, 0
        for doc in get_employees_from_crm_document():
            is_created, is_updated_from_hr_id, is_updated_from_email = update_employee_from_from_csv(doc)
            if is_created:
                created += 1
            elif is_updated_from_hr_id:
                updated_from_hr_id += 1
            elif is_updated_from_email:
                updated_from_email += 1

        print('Created: %i\nUpdated from hr id: %i\nUpdated from email: %i' % (created, updated_from_hr_id, updated_from_email))
