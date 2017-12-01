
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
    rhs = timestamp.value
    cursor = None

    while True:
        body = {
            'page_size': '25',
            'global_sort_key': 'created_time',
            'filterJson': json.dumps({
                'rules': [{'LHS': 'created_time', 'CONDITION': 'AFTER', 'RHS': rhs * 1000 - 86400000}],
                'contact_type': 'COMPANY'})}
        if cursor:
            body['cursor'] = cursor
            cursor = None

        conn.request('POST', '/dev/api/filters/filter/dynamic-filter',
                     body=urlencode(body), headers=REQUEST_HEADER)
        resp = conn.getresponse()

        assert resp.status == 200
        bbody = resp.read()
        patients_doc = json.loads(bbody.decode())

        c = 0
        if patients_doc:
            for doc in patients_doc:
                if doc.get('updated_time', 0) != 0:
                    continue
                update_patient(conn, doc)
                c += 1
                timestamp.value = max(timestamp.value, doc['created_time'])
            timestamp.save()

        if not cursor:
            break

    # Sync updated
    timestamp, _ = UkumpGlobal.objects.get_or_create(key='agilecrm_patients_sync_timestamp', defaults={'value': 0})
    rhs = timestamp.value
    while True:
        body = {
            'page_size': '25',
            'global_sort_key': 'updated_time',
            'filterJson': json.dumps({
                'rules': [{'LHS': 'updated_time', 'CONDITION': 'AFTER', 'RHS': rhs * 1000 - 86400000}],
                'or_rules': [],
                'contact_type': 'COMPANY'
            })}
        if cursor:
            body['cursor'] = cursor
            cursor = None

        conn.request('POST', '/dev/api/filters/filter/dynamic-filter',
                     body=urlencode(body), headers=REQUEST_HEADER)
        resp = conn.getresponse()

        assert resp.status == 200
        bbody = resp.read()
        patients_doc = json.loads(bbody.decode())

        if patients_doc:
            for doc in patients_doc:
                c += 1
                update_patient(conn, doc)
                cursor = doc.get('cursor')
                timestamp.value = max(timestamp.value, doc['updated_time'])

            timestamp.save()
        if not cursor:
            break

    conn.close()
    return c


def sync_customers():
    timestamp, _ = UkumpGlobal.objects.get_or_create(key='agilecrm_customer_sync_timestamp', defaults={'value': 0})
    cursor = None
    rhs = timestamp.value

    while True:
        body = {
            'page_size': '25',
            'global_sort_key': 'updated_time',
            'filterJson': json.dumps({
                'rules': [{'LHS': 'updated_time', 'CONDITION': 'AFTER', 'RHS': rhs * 1000 - 86400000}],
                'contact_type': 'PERSON'})}
        if cursor:
            body['cursor'] = cursor
            cursor = None

        conn = HTTPSConnection(DOMAIN)
        conn.request('POST', '/dev/api/filters/filter/dynamic-filter',
                     body=urlencode(body), headers=REQUEST_HEADER)
        resp = conn.getresponse()

        assert resp.status == 200
        bbody = resp.read()
        customers_doc = json.loads(bbody.decode())

        c = 0
        if customers_doc:
            for doc in customers_doc:
                customer = Customer.objects.filter(profile__agilrcrm=doc['id']).order_by('id').first()
                if customer:
                    c += 1
                    update_customer(customer, doc)
                timestamp.value = max(timestamp.value, max(doc['updated_time'], doc['created_time']))
                cursor = doc.get('cursor')
            timestamp.save()
            time.sleep(1.0)

        if not cursor:
            break

    conn.close()
    return c


@transaction.atomic
def update_patient(conn, doc):
    print(doc)
    print("\n\n")
    patient = Patient.objects.filter(extend__agilrcrm=doc['id']).order_by('id').first()
    if not patient:
        patient = Patient(extend={'agilrcrm': doc['id']})
    attrs = {p['name']: p['value'] for p in doc['properties']}
    patient.name = attrs['Case Name']

    patient.extend['case_id'] = attrs['name']
    if 'Date of Birth' in attrs:
        patient.birthday = time.strftime('%Y-%m-%d', time.gmtime(int(attrs['Date of Birth'])))
    if 'Gender' in attrs:
        patient.extend['sex'] = attrs['Gender']
    if 'Appellation' in attrs:
        patient.extend['title'] = attrs['Appellation']
    if 'Last Bill' in attrs:
        url = attrs['Last Bill']
        if url.startswith('http://') or url.startswith('https://'):
            patient.extend['bill_url'] = url
    if 'Online Payment' in attrs:
        url = attrs['Online Payment']
        if url.startswith('http://') or url.startswith('https://'):
            patient.extend['payment_url'] = url

    patient.save()

    patient.guardian_set.filter(master=True).delete()
    if 'Contact Window' in attrs:
        for crm_customer_id in map(int, json.loads(attrs['Contact Window'])):
            c = Customer.objects.filter(profile__agilrcrm=crm_customer_id).order_by('id').first()
            if not c:
                c = create_customer(conn, crm_customer_id)
            g = patient.guardian_set.filter(customer=c).first()
            if g:
                g.relation = patient.extend.get('title', '未填寫')
                g.master = True
                g.save()
            else:
                patient.guardian_set.create(customer=c, relation=patient.extend.get('title', '未填寫'), master=True)

    employee = update_employee(doc['owner'])
    relations = patient.manager_set.filter(relation='照護經理')
    if relations.count() == 1:
        relation = relations[0]
        if relation.employee_id != employee.id:
            relation.employee = employee
            relation.save()
    else:
        if relations.count() > 1:
            relations.delete()
        patient.manager_set.create(employee=employee, relation='照護經理')


def update_employee(doc):
    employee = Employee.objects.filter(profile__agilecrm=doc['id']).order_by('id').first()
    if not employee:
        employee = Employee(profile={'agilecrm': doc['id']}, members=[])
    employee.name = doc['name']
    employee.profile['email'] = doc.get('email')
    employee.profile['phone'] = doc.get('phone', '').replace('-', '')
    employee.save()
    return employee


def create_customer(conn, crm_customer_id):
    conn.request('GET', '/dev/api/contacts/%s' % crm_customer_id, headers=REQUEST_HEADER)
    resp = conn.getresponse()
    assert resp.status == 200

    bbody = resp.read()
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
        customer.phone = profile['phone'] = attrs['phone'].replace('-', '')
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
    name = source.name
    email = source.profile.get('email', 'noemail@ukump.com') if source.profile else 'noemail@ukump.com'

    conn = HTTPSConnection(DOMAIN)
    body = json.dumps({
        "requester_name": name,
        "requester_email": email,
        "subject": title,
        "priority": "HIGH" if emergency else "MEDIUM",
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

        bbody = resp.read()
        doc = json.loads(bbody.decode())
        return doc['id'], 'https://ukump.agilecrm.com/#ticket/%s' % doc['id']
    except Exception:
        print(resp.read())
        raise


def get_patient_crm_url(patient):
    return 'https://ukump.agilecrm.com/#company/%s' % patient.extend['agilrcrm']
