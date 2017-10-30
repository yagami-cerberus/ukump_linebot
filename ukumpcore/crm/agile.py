
from http.client import HTTPSConnection
from urllib.parse import urlencode
from django.conf import settings
from django.db import transaction
from itertools import groupby
from base64 import b64encode
import time
import json

from customer.models import Profile as Customer
from employee.models import Profile as Employee
from patient.models import Profile as Patient
from patient.models import UkumpGlobal


DOMAIN = settings.AGILECRM_DOMAIN
REQUEST_HEADER = {
    'Accept': 'application/json',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Authorization': ('Basic %s' % (b64encode(('%s:%s' % (settings.AGILECRM_USERNAME, settings.AGILECRM_TOKEN)).encode()).decode(), ))
}
TICKET_REQUEST_HEADER = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Authorization': REQUEST_HEADER['Authorization']
}


def sync_patients():
    conn = HTTPSConnection(DOMAIN)

    # Sync created but not updated yet
    timestamp, _ = UkumpGlobal.objects.get_or_create(key='agilecrm_patients_create_timestamp', defaults={'value': 0})
    body = urlencode({
        'page_size': '25',
        'global_sort_key': 'created_time',
        'filterJson': json.dumps({
            'rules': [{'LHS': 'created_time', 'CONDITION': 'AFTER', 'RHS': timestamp.value}],
            'contact_type': 'COMPANY'
        })
    })
    conn.request('POST', '/dev/api/filters/filter/dynamic-filter',
                 body=body, headers=REQUEST_HEADER)
    resp = conn.getresponse()

    assert resp.status == 200
    bbody = resp.readall()
    patients_doc = json.loads(bbody.decode())

    if patients_doc:
        for doc in patients_doc:
            if doc.get('updated_time', 0) != 0:
                continue
            update_patient(conn, doc)
        timestamp.value = patients_doc[-1]['created_time']
        timestamp.save()

    # Sync updated
    timestamp, _ = UkumpGlobal.objects.get_or_create(key='agilecrm_patients_sync_timestamp', defaults={'value': 0})
    body = urlencode({
        'page_size': '25',
        'global_sort_key': 'updated_time',
        'filterJson': json.dumps({
            'rules': [{'LHS': 'updated_time', 'CONDITION': 'AFTER', 'RHS': timestamp.value}],
            'contact_type': 'COMPANY'
        })
    })
    conn.request('POST', '/dev/api/filters/filter/dynamic-filter',
                 body=body, headers=REQUEST_HEADER)
    resp = conn.getresponse()

    assert resp.status == 200
    bbody = resp.readall()
    patients_doc = json.loads(bbody.decode())

    if patients_doc:
        for doc in patients_doc:
            update_patient(conn, doc)
        timestamp.value = patients_doc[-1]['updated_time']
        timestamp.save()

    conn.close()


def sync_customers():
    timestamp, _ = UkumpGlobal.objects.get_or_create(key='agilecrm_customer_sync_timestamp', defaults={'value': 0})
    body = urlencode({
        'page_size': '25',
        'global_sort_key': 'updated_time',
        'filterJson': json.dumps({
            'rules': [{'LHS': 'updated_time', 'CONDITION': 'AFTER', 'RHS': 1508688000000}],
            'contact_type': 'PERSON'
        })
    })
    conn = HTTPSConnection(DOMAIN)
    conn.request('POST', '/dev/api/filters/filter/dynamic-filter',
                 body=body, headers=REQUEST_HEADER)
    resp = conn.getresponse()

    assert resp.status == 200
    bbody = resp.readall()
    customers_doc = json.loads(bbody.decode())

    if customers_doc:
        for doc in customers_doc:
            customer = Customer.objects.filter(profile__agilrcrm=doc['id']).order_by('id').first()
            if customer:
                update_customer(customer, doc)
        timestamp.value = customers_doc[-1]['updated_time'] or customers_doc[-1]['created_time']
        timestamp.save()
    conn.close()


@transaction.atomic
def update_patient(conn, doc):
    patient = Patient.objects.filter(extend__agilrcrm=doc['id']).order_by('id').first()
    if not patient:
        patient = Patient(extend={'agilrcrm': doc['id']})
    attrs = {p['name']: p['value'] for p in doc['properties']}
    patient.name = attrs['name']
    if 'Date of Birth' in attrs:
        patient.birthday = time.strftime('%Y-%m-%d', time.gmtime(int(attrs['Date of Birth'])))
    if 'Gender' in attrs:
        patient.extend['sex'] = attrs['Gender']
    patient.save()

    if 'Contact Window' in attrs:
        for crm_customer_id in map(int, json.loads(attrs['Contact Window'])):
            c = Customer.objects.filter(profile__agilrcrm=crm_customer_id).order_by('id').first()
            if not c:
                c = create_customer(conn, crm_customer_id)
            if not patient.guardian_set.filter(customer=c):
                patient.guardian_set.create(customer=c, relation="Master")


def create_customer(conn, crm_customer_id):
    conn.request('GET', '/dev/api/contacts/%s' % crm_customer_id, headers=REQUEST_HEADER)
    resp = conn.getresponse()
    assert resp.status == 200

    bbody = resp.readall()
    doc = json.loads(bbody.decode())

    customer = Customer(profile={'agilrcrm': crm_customer_id})
    update_customer(customer, doc)
    return customer


@transaction.atomic
def update_customer(customer, crm_profile):
    attrs = {name: next(vals)['value'] for name, vals in groupby(crm_profile['properties'], lambda p: p['name'])}

    customer.name = '%s%s' % (attrs.get('last_name', ''), attrs.get('first_name', ''))
    profile = customer.profile
    if 'phone' in attrs:
        profile['phone'] = attrs['phone']
    if 'email' in attrs:
        profile['email'] = attrs['email']
    if 'email' in attrs:
        profile['email'] = attrs['email']
    customer.save()


def customer_support_crm(customer):
    return customer.profile and "agilrcrm" in customer.profile


def customer_support_crm_filter(queryset):
    return queryset.filter(profile__agilrcrm__isnull=False)


def create_crm_ticket(source, title, body, emergency=False):
    if isinstance(source, Customer):
        name = source.name
        email = source.profile['email']
    elif isinstance(source, Employee):
        name = source.name
        email = source.extend['email']

    conn = HTTPSConnection(DOMAIN)
    body = json.dumps({
        "requester_name": name,
        "requester_email": email,
        "subject": title,
        "priority": "HIGH" if emergency else "NORMAL",
        "status": "OPEN",
        "groupID": "5649202965118976",
        "html_text": body,
        "cc_emails": [],
        "labels": None
    })
    conn.request('POST', '/dev/api/tickets/new-ticket',
                 body=body, headers=TICKET_REQUEST_HEADER)
    resp = conn.getresponse()
    try:
        assert resp.status == 200

        bbody = resp.readall()
        doc = json.loads(bbody.decode())
        return doc['id'], 'https://ukump.agilecrm.com/#ticket/%s' % doc['id']
    except Exception:
        print(resp.readall())
        raise


def get_patient_crm_url(patient):
    return 'https://ukump.agilecrm.com/#company/%s' % patient.extend['agilrcrm']
