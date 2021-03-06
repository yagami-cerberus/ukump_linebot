
from psycopg2.extras import DateTimeTZRange
from http.client import HTTPSConnection
from urllib.request import urlopen
from urllib.parse import urlencode
from django.conf import settings
from django.db import transaction
from itertools import groupby
from datetime import datetime, timedelta
from dateutil import parser
from base64 import b64encode
from io import StringIO
import time
import json
import csv

from customer.models import Profile as Customer
from employee.models import Profile as Employee
from patient.models import Profile as Patient, NursingSchedule
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
                customer = Customer.objects.filter(profile__agilecrm=doc['id']).order_by('id').first()
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
    patient = Patient.objects.filter(extend__agilecrm=doc['id']).order_by('id').first()
    if not patient:
        patient = Patient(extend={'agilecrm': doc['id']})
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

    crm_guardians = set()
    crm_master_guardians = set()
    if 'Family Members' in attrs:
        for crm_customer_id in json.loads(attrs['Family Members']):
            crm_guardians.add(int(crm_customer_id))
    if 'Contact Window' in attrs:
        for crm_customer_id in json.loads(attrs['Contact Window']):
            crm_guardians.add(int(crm_customer_id))
            crm_master_guardians.add(int(crm_customer_id))

    for g in patient.guardian_set.select_related('customer').all():
        crm_customer_id = g.customer.profile.get('agilecrm')
        if crm_customer_id in crm_guardians:
            crm_guardians.remove(crm_customer_id)
            g.master = crm_customer_id in crm_master_guardians
            g.save()
        else:
            g.delete()

    for crm_customer_id in crm_guardians:
        c = Customer.objects.filter(profile__agilecrm=crm_customer_id).order_by('id').first()
        if not c:
            c = create_customer(conn, crm_customer_id)
        g = patient.guardian_set.filter(customer=c).first()
        if g:
            g.relation = patient.extend.get('title', '未填寫')
            g.master = crm_customer_id in crm_master_guardians
            g.save()
        else:
            patient.guardian_set.create(customer=c, relation=patient.extend.get('title', '未填寫'), master=crm_customer_id in crm_master_guardians)

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

    customer = Customer(profile={'agilecrm': crm_customer_id})
    update_customer(customer, doc)
    return customer


@transaction.atomic
def update_customer(customer, crm_profile):
    attrs = {name: next(vals)['value'] for name, vals in groupby(crm_profile['properties'], lambda p: p['name'])}

    customer.name = '%s%s' % (attrs.get('first_name', ''), attrs.get('last_name', ''))
    profile = customer.profile
    if 'phone' in attrs:
        customer.phone = profile['phone'] = attrs['phone'].replace('-', '')
    if 'email' in attrs:
        profile['email'] = attrs['email']
    if 'email' in attrs:
        profile['email'] = attrs['email']
    customer.save()


def customer_support_crm(customer):
    return customer.profile and "agilecrm" in customer.profile


def customer_support_crm_filter(queryset):
    return queryset.filter(profile__agilecrm__isnull=False)


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
    return 'https://ukump.agilecrm.com/#company/%s' % patient.extend['agilecrm']


def update_crm_guardian(patient):
    conn = HTTPSConnection(DOMAIN)
    meta = patient.guardian_set.filter(customer__profile__agilecrm__isnull=False).values_list('customer__profile', flat=True)
    values = list(str(m['agilecrm']) for m in meta)

    body = json.dumps({
        'id': patient.extend['agilecrm'],
        'properties': [
            {
                'name': 'Family Members',
                'type': 'CUSTOM',
                'value': json.dumps(values)
            }
        ]
    })

    conn.request('PUT', '/dev/api/contacts/edit-properties',
                 body=body, headers=TICKET_REQUEST_HEADER)
    resp = conn.getresponse()
    try:
        assert resp.status == 200
        print(resp.read())
    except Exception:
        print(resp.status, resp.read())
        raise


def create_crm_contect(name, email, phone):
    conn = HTTPSConnection(DOMAIN)
    body = json.dumps({
        'tags': ['邀請碼註冊'],
        'properties': [
            {
                "type": "SYSTEM",
                "name": "first_name",
                "value": name
            },
            {
                "type": "SYSTEM",
                "name": "email",
                "subtype": "work",
                "value": email
            },
            {
                "name": "phone",
                "value": phone,
                "subtype": "work"
            }
        ]
    })
    conn.request('POST', '/dev/api/contacts',
                 body=body, headers=TICKET_REQUEST_HEADER)
    resp = conn.getresponse()

    try:
        assert resp.status == 200

        bbody = resp.read()
        doc = json.loads(bbody.decode())

        customer = Customer(profile={'agilecrm': int(doc['id'])})
        update_customer(customer, doc)
        customer.save()

        return customer
    except Exception:
        print(resp.status, resp.read())
        raise


def get_crm_document(doc_name):
    conn = HTTPSConnection(DOMAIN)

    conn.request('GET', '/dev/api/documents/contact/5692767623708672/docs',
                 headers=REQUEST_HEADER)
    resp = conn.getresponse()

    assert resp.status == 200
    bbody = resp.read()
    doc_lists = json.loads(bbody.decode())
    for doc in doc_lists:
        if doc['name'] == doc_name and doc['extension'].endswith('.csv'):
            resp = urlopen(doc['url'])
            assert resp.status == 200
            return resp
    else:
        raise RuntimeError('找不到名稱為 %s 的 .csv 文件' % doc_name)


def get_employees_from_crm_document(doc_name='UKump-Empl-LINE-Sync'):
    resp = get_crm_document(doc_name)
    f = StringIO(resp.read().decode())
    reader = csv.reader(f)
    if '公司名稱：由康照護股份有限公司' not in next(reader)[0]:
        raise RuntimeError('未預期的資料格式')
    if '資料類型：員工資料匯出' not in next(reader)[0]:
        raise RuntimeError('未預期的資料格式')
    for i in range(5):
        next(reader)
    if next(reader) != ['', '員工編號', '姓名', '生日', '英文姓名', '性別', '國籍', '婚姻狀況', '身份族群', '身心障礙類別', '兵役狀況', '公司電話', '行動電話', '公司email', '通訊地址', '聯絡人姓名/關係', '聯絡人電話', '個人email', '戶籍地址', '到職日期', '試滿日期', '部門', '員工類型', '職務類別', '職位', '責任區分', '直/間接人員', '編制狀態', '在職狀態', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '']:
        raise RuntimeError("員工匯入欄位格式不符合預期")

    for line in reader:
        yield {
            'hr_id': line[1],
            'name': line[2],
            'phone': line[12],
            'email': line[13],
            'title': line[23]
        }


def update_employee_from_from_csv(doc):
    employee = Employee.objects.filter(profile__hr_id=doc['hr_id']).order_by('id').first()
    if employee:
        employee.name = doc['name']
        employee.profile['email'] = doc['email']
        employee.profile['phone'] = doc.get('phone', '').replace('-', '')
        employee.profile['title'] = doc['title']
        employee.save()
        return False, True, False

    employee = Employee.objects.filter(profile__email=doc['email']).order_by('id').first()
    if employee:
        employee.name = doc['name']
        employee.profile['hr_id'] = doc['hr_id']
        employee.profile['phone'] = doc.get('phone', '').replace('-', '')
        employee.profile['title'] = doc['title']
        employee.save()
        return False, False, True

    employee = Employee(name=doc['name'], profile={'hr_id': doc['hr_id'],
                                                   'phone': doc['phone'],
                                                   'title': doc['title']}, members=[])
    employee.save()
    return True, False, False


def get_schedule_from_crm_document(doc_name='UKump-Schedule-LINE-Sync'):
    resp = get_crm_document(doc_name)
    f = StringIO(resp.read().decode())
    reader = csv.reader(f)
    if '由康照護股份有限公司' not in next(reader)[0]:
        raise RuntimeError('未預期的資料格式')
    if next(reader)[:6] != ['員工編號', '合約編號', '性質', '日期', '開始時間', '服務時數']:
        raise RuntimeError("班表匯入欄位格式不符合預期")

    for line in reader:
        yield {
            'hr_id': line[0],
            'case_id': line[1],
            'type': line[2],
            'date': line[3],
            'start_time': line[4],
            'duration': line[5]
        }


def update_schedule_from_csv(doc, today, tzinfo):
    try:
        date = parser.parse(doc['date']).date()
    except ValueError:
        raise RuntimeError('無法處理排程日期欄位: %s' % doc['date'])

    if date <= today:
        return False

    try:
        time = parser.parse(doc['start_time'])
    except ValueError:
        raise RuntimeError('無法處理排程時間欄位: %s' % doc['start_time'])

    begin_at = datetime(date.year, date.month, date.day,
                        time.hour, time.minute, time.second,
                        tzinfo=tzinfo)
    try:
        end_at = begin_at + timedelta(hours=float(doc['duration']))
    except ValueError:
        raise RuntimeError('無法處理服務時數欄位: %s' % doc['duration'])

    if end_at.date() != begin_at.date():
        raise RuntimeError('服務時間不能跨日，日期 %s, 員工編號 %s, 個案 %s' % (date, doc['hr_id'], doc['case_id']))

    try:
        employee = Employee.objects.filter(profile__hr_id=doc['hr_id']).get()
    except Employee.DoesNotExist:
        raise RuntimeError('員工編號 %s 不存在' % doc['hr_id'])
    except Employee.MultipleObjectsReturned:
        raise RuntimeError('員工編號 %s 對應到超過一位員工' % doc['hr_id'])

    try:
        patient = Patient.objects.filter(extend__case_id=doc['case_id']).get()
    except Patient.DoesNotExist:
        raise RuntimeError('合約編號 %s 不存在' % doc['case_id'])
    except Patient.MultipleObjectsReturned:
        raise RuntimeError('合約編號 %s 對應到超過一個案例' % doc['case_id'])

    if doc['type'] == '照護':
        NursingSchedule(
            patient=patient, employee=employee,
            schedule=DateTimeTZRange(begin_at, end_at)
        ).save()
        return True
    else:
        raise RuntimeError('不認識的服務類別: %s' % doc['type'])
