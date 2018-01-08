
from django.utils.crypto import get_random_string
from django.core.cache import cache
from django.shortcuts import render, redirect
from django.contrib import messages

from ukumpcore.linebot_utils import line_bot, require_lineid, get_customer_from_lineid, get_employee_from_lineid
from ukumpcore.crm.agile import create_crm_contect, update_crm_guardian
from customer.models import Profile as Customer, LineBotIntegration as CustomerLine
from employee.models import Profile as Employee, LineBotIntegration as EmployeeLine
from patient.models import Profile as Patient, Guardian


def send_sns(validate_code, pnum):
    import boto3
    sns = boto3.client('sns', region_name='us-west-2',
                       aws_access_key_id='AKIAJBQPIFJNHGKXI3EA',
                       aws_secret_access_key='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')
    sns.publish(Message='您在由康照護的驗證碼為 %s ' % validate_code, PhoneNumber='+886' + pnum[1:])


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
        if request.method == 'POST':
            return redirect('line_association', role=role)

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
                send_sns(validate_code, cnum)
                messages.info(request, '認證碼已送出')
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
            messages.error(request, '電話號碼不存在，如果您是案例家屬請向照護經理取得邀請碼。')
            return cls.render(request, 'customer')
        except Patient.MultipleObjectsReturned:
            messages.error(request, '電話號碼異常，請直接聯絡照護經理。')
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
            send_sns(validate_code, pnum)
            messages.info(request, '認證碼已送出')
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
        crel = request.POST.get('crel', '')
        cinv = request.POST.get('cinv', '')

        cache_key = '_line_asso_invcode:%s' % cinv
        patient_id = cache.get(cache_key)

        if not cname or not cnum or not cemail:
            messages.error(request, '請填寫表格')
            return cls.render(request, 'guest')
        elif Customer.objects.filter(profile__phone=cnum).count():
            messages.error(request, '此電話號碼已經完成註冊，請使用客戶身份進行認證')
            return redirect('line_association', role='customer')
        elif Customer.objects.filter(profile__email=cemail.lower()).count():
            messages.error(request, '此電子郵件已經完成註冊，請使用客戶身份進行認證')
            return redirect('line_association', role='customer')
        elif not patient_id:
            messages.error(request, '無效的邀請碼，請向照護經理確認')
            return cls.render(request, 'guest')
        else:
            if request.POST.get('submit') == 'check':
                validate_code = get_random_string(8, allowed_chars='1234567890')

                request.session['gmatch'] = (cnum, cname, cemail, crel, cinv, validate_code)
                send_sns(validate_code, cnum)
                messages.info(request, '認證碼已送出')
                return cls.render(request, 'guest', confirm=True)

            else:
                cnum, cname, cemail, crel, cinv, validate_code = request.session.get('gmatch', (None, None, None, None, None, None))

                if request.POST.get('confirm-code') == validate_code:
                    customer = create_crm_contect(name=cname, email=cemail, phone=cnum)
                    cache.delete(cache_key)

                    customer.save()
                    CustomerLine(lineid=line_id, customer=customer).save()
                    Guardian(customer=customer, patient_id=patient_id, relation=crel).save()
                    update_crm_guardian(Patient.objects.get(pk=patient_id))

                    return cls.render_completed(request, 'customer', customer)
                else:
                    messages.error(request, '錯誤的驗證碼')
                    return cls.render(request, 'guest', require_profile=True, confirm=True)
