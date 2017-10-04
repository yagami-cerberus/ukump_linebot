
from django.shortcuts import redirect
from django.utils import timezone
from django.urls import reverse

from urllib.parse import quote
import pytz

from employee.models import Profile as Employee, LineBotIntegration as EmployeeLineBotIntegration
from customer.models import Profile as Customer, LineBotIntegration as CustomerLineBotIntegration

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


def localtime():
    return timezone.localtime(timezone=fix_tz)


def require_lineid(fn):
    def wrapper(request, *args, **kw):
        if 'line_id' not in request.session:
            return redirect(reverse('linelogin') + '?url=' + quote(request.get_full_path()))
        else:
            return fn(request, *args, **kw)
    return wrapper
