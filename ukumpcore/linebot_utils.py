
from linebot.models import PostbackTemplateAction, CarouselColumn
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.utils import timezone
from django.urls import reverse
from collections import namedtuple
from urllib.parse import quote
import pytz
import json

from patient.models import Profile as Patient
from employee.models import Profile as Employee, LineBotIntegration as EmployeeLineBotIntegration
from customer.models import Profile as Customer, LineBotIntegration as CustomerLineBotIntegration

Cases = namedtuple('Cases', ['owner', 'patients'])
Patients = namedtuple('Patients', ['manager', 'nurse', 'customer'])
fix_tz = pytz.timezone('Etc/GMT-8')


def get_employees_lineid(employees):
    return EmployeeLineBotIntegration.objects.filter(employee__in=employees).values_list('lineid', flat=True)


def get_employee_id_from_lineid(lineid):
    return EmployeeLineBotIntegration.objects.filter(lineid=lineid).values_list('employee_id', flat=True).first()


def get_employee_id(event):
    if event.source.type == "user":
        return get_employee_id_from_lineid(event.source.user_id)


def get_employee_from_lineid(lineid):
    pk = EmployeeLineBotIntegration.objects.filter(lineid=lineid).values_list('employee_id', flat=True).first()
    if pk is not None:
        return Employee.objects.filter(pk=pk).first()


def get_employee(event):
    if event.source.type == "user":
        return get_employee_from_lineid(event.source.user_id)


def get_customer_lineid(customer):
    return CustomerLineBotIntegration.objects.filter(customer=customer).values_list('lineid', flat=True)


def get_customer_id_from_lineid(lineid):
    return CustomerLineBotIntegration.objects.filter(lineid=lineid).values_list('customer_id', flat=True).first()


def get_customer_id(event):
    if event.source.type == "user":
        return get_customer_id_from_lineid(event.source.user_id)


def get_customer_from_lineid(lineid):
    pk = CustomerLineBotIntegration.objects.filter(lineid=lineid).values_list('customer_id', flat=True).first()
    if pk is not None:
        return Customer.objects.filter(pk=pk).first()


def get_customer(event):
    if event.source.type == "user":
        return get_customer_from_lineid(event.source.user_id)


def get_patients(event):
    employee = get_employee(event)
    customer = get_customer(event)

    if employee:
        manager_cases = employee.patients.all()
        nursing_cases = Patient.objects.filter(id__in=employee.nursing_schedule.today_schedule().values_list("patient_id", flat=True))
    else:
        manager_cases = nursing_cases = Patient.objects.none()

    customer_cases = customer.patients.all() if customer else Patient.objects.none()

    return Patients(
        Cases(employee, manager_cases),
        Cases(employee, nursing_cases),
        Cases(customer, customer_cases)
    )


def generate_patients_card(title, text, params, patients, label=lambda x: x.name, value=lambda x: x.id):
    l = len(patients)
    columns = []
    for i in range(0, l, 3):
        actions = []
        for j in range(i, min(i + 3, l)):
            p = patients[j]
            data = params.copy()
            data['V'] = value(p)
            actions.append(PostbackTemplateAction(
                label(p),
                json.dumps(data)))
        while len(actions) != 3:
            actions.append(PostbackTemplateAction(
                '-',
                '{"T": ""}'))
        columns.append(CarouselColumn(title=title, text=text, actions=actions))
    return columns


def localtime():
    return timezone.localtime(timezone=fix_tz)


def require_lineid(fn):
    def wrapper(request, *args, **kw):
        if 'line_id' not in request.session:
            return redirect(reverse('linelogin') + '?url=' + quote(request.get_full_path()))
        else:
            return fn(request, *args, **kw)
    return wrapper


def is_system_admin(event):
    model = get_user_model()


class LineMessageError(RuntimeError):
    pass


class NotMemberError(RuntimeError):
    pass


not_member_error = NotMemberError()
