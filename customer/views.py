
from django.utils.crypto import get_random_string
from django.core.cache import cache
from django.shortcuts import render, redirect
from django.contrib import messages
import json

from ukumpcore.linebot_utils import line_bot, require_lineid, get_customer_from_lineid, get_employee_from_lineid
from patient.models import Profile as Patient
from customer.models import Profile as Customer, LineBotIntegration as CustomerLine
from employee.models import Profile as Employee, LineBotIntegration as EmployeeLine


@require_lineid
class LineAssociation(object):
    def __new__(cls, request, role):
        line_id = request.session['line_id']

        if role == 'employee':
            employee = get_employee_from_lineid(line_id)
            if employee:
                return cls.render_completed(request, 'employee', employee)
        if role == 'customer' or role == 'guest':
            customer = get_customer_from_lineid(line_id)
            if customer:
                return cls.render_completed(request, 'customer', customer)

        if request.method == 'GET':
            return cls.get(request, line_id, role)
        elif request.method == 'POST':
            return cls.post(request, line_id, role)

    @classmethod
    def render(cls, request, role, confirm=False, source=None, require_profile=None):
        if role:
            return render(request, 'customer/association_%s.html' % role,
                          {'confirm': confirm, 'source': source, 'require_profile': require_profile})
        else:
            return render(request, 'customer/association.html')

    @classmethod
    def render_completed(cls, request, role, source):
        line_profiles = []
        for line_id in source.linebotintegration_set.values_list('lineid', flat=True):
            try:
                line_profiles.append(line_bot.get_profile(line_id).as_json_dict())
            except Exception:
                line_profiles.append({'userId': line_id})

        return render(request, 'customer/association_completed.html', {
            'role': role, 'source': source, 'line_profiles': line_profiles})

    @classmethod
    def get(cls, request, line_id, role=None):
        if role == 'associate':
            return cls.render_completed(request, 'customer', get_customer_from_lineid(line_id))
        else:
            return cls.render(request, role)

    @classmethod
    def post(cls, request, line_id, role=None):
        if role == 'customer':
            return cls.post_customer(request, line_id)
        elif role == 'employee':
            return cls.post_employee(request, line_id)
        elif role == 'guest':
            return cls.post_guest(request, line_id)
        elif role == 'associate':
            return cls.post_associate(request, line_id)

    @classmethod
    def post_customer(cls, request, line_id):
        cnum = request.POST.get('pnum', '').replace('-', '')

        try:
            customer = Customer.objects.get(profile__phone=cnum)

            if request.POST.get('submit') == 'check':
                validate_code = get_random_string(8, allowed_chars='1234567890')
                request.session['cmatch'] = (cnum, customer.name, None, validate_code)
                messages.info(request, '認證碼已送出 (%s)' % validate_code)
                return cls.render(request, 'customer', confirm=True)
            else:
                cnum, _, _, validate_code = request.session.get('cmatch', (None, None, None, None))
                if request.POST.get('confirm-code') == validate_code:
                    CustomerLine(lineid=line_id, customer=customer).save()
                    return cls.render_completed(request, 'customer', customer)
                else:
                    messages.error(request, '錯誤的驗證碼')
                    return cls.render(request, 'customer', require_profile=True, confirm=True)
        except Customer.DoesNotExist:
            messages.error(request, '錯誤的電話號碼')
            return cls.render(request, 'customer')
        except Patient.MultipleObjectsReturned:
            messages.error(request, '電話號碼異常，請直接聯絡照護經理')
            return cls.render(request, 'customer')

    @classmethod
    def post_employee(cls, request, line_id):
        pnum = request.POST.get('pnum', '').replace('-', '')

        try:
            employee = Employee.objects.get(profile__phone=pnum)
        except Employee.DoesNotExist:
            messages.error(request, '錯誤的電話號碼')
            return cls.render(request, 'employee')
        except Employee.MultipleObjectsReturned:
            messages.error(request, '員工資料異常，請直接聯絡照護經理')
            return cls.render(request, 'employee')

        if request.POST.get('submit') == 'check':
            validate_code = get_random_string(8, allowed_chars='1234567890')
            request.session['ematch'] = (validate_code, employee.id)

            messages.info(request, '認證碼已送出 (%s)' % validate_code)
            return cls.render(request, 'employee', confirm=True)

        else:
            validate_code, patient_id = request.session.get('ematch', (None, None))
            if request.POST.get('confirm-code') == validate_code:
                EmployeeLine(lineid=line_id, employee=employee).save()
                request.session.pop('ematch')
                return cls.render_completed(request, 'employee', employee)
            else:
                messages.error(request, '錯誤的驗證碼')
                return cls.render(request, 'employee', confirm=True)

    @classmethod
    def post_guest(cls, request, line_id):
        cnum = request.POST.get('cnum', '').replace('-', '')
        cname = request.POST.get('cname', '')
        cemail = request.POST.get('cemail', '')
        customers = Customer.objects.filter(profile__phone=cnum)

        if customers:
            messages.error(request, '此電話號碼已經完成註冊，請使用客戶身份進行認證')
            return redirect('line_association', role='customer')
        elif not cname or not cnum or not cemail:
            messages.error(request, '請填寫表格')
            return cls.render(request, 'guest')
        else:
            if request.POST.get('submit') == 'check':
                validate_code = get_random_string(8, allowed_chars='1234567890')
                request.session['gmatch'] = (cnum, cname, cemail, validate_code)
                messages.info(request, '認證碼已送出 (%s)' % validate_code)
                return cls.render(request, 'guest', confirm=True)
            else:
                cnum, cname, cemail, validate_code = request.session.get('gmatch', (None, None, None, None))
                if request.POST.get('confirm-code') == validate_code:
                    customer = Customer(name=cname, phone=cnum, profile={'email': cemail})
                    customer.save()
                    CustomerLine(lineid=line_id, customer=customer).save()
                    return cls.render_completed(request, 'customer', customer)
                else:
                    messages.error(request, '錯誤的驗證碼')
                    return cls.render(request, 'guest', require_profile=True, confirm=True)

    @classmethod
    def post_associate(cls, request, line_id):
        customer = get_customer_from_lineid(line_id)
        case_id = request.POST.get('patient_case_id')
        relation = request.POST.get('patient_relation')

        try:
            patient = Patient.objects.get(extend__case_id=case_id)
            if patient.customers.filter(id=customer.id):
                messages.error(request, '重複加入個案')
            else:
                master = patient.customers.get(guardian__master=True)
                if master.linebotintegration_set.count():
                    cache.set('_line_asso_add:%i_%i' % (patient.id, customer.id), relation, 86400)

                    message = {
                        'M': 'confirm',
                        'text': '%s 請求加入 %s 的照護群組\n聯絡電話：%s' % (customer.name, patient.name, customer.phone),
                        'actions': (
                            {'type': 'postback', 'label': '確認', 'data': json.dumps({'T': 'association', 'value': (True, patient.id, customer.id)})},
                            {'type': 'postback', 'label': '撤銷', 'data': json.dumps({'T': 'association', 'value': (False, patient.id, customer.id)})},
                        )
                    }
                    master.push_raw_message(json.dumps(message))

                    messages.info(request, '已經提出加入請求，請等待回覆')
                else:
                    messages.error(request, '主要客戶未完成註冊，無法執行這個請求')

        except Patient.DoesNotExist:
            messages.error(request, '錯誤的合約號碼')
        except Patient.MultipleObjectsReturned:
            messages.error(request, '合約號碼異常，請聯絡客服人員')

        return cls.render_completed(request, 'customer', customer)
