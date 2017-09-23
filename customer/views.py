
from django.utils.crypto import get_random_string
from django.shortcuts import render, redirect
from django.contrib import messages
# from django.urls import reverse
import json

from ukumpcore.line_utils import require_lineid
from patient.models import Profile as PatientProfile, Guardian
from customer.models import Profile as CustomerProfile, LineBotIntegration


@require_lineid
def line_association(request):
    line_id = request.session['line_id']

    if request.method == 'GET':

        if LineBotIntegration.objects.filter(lineid=line_id).exists():
            return redirect('patient_main')
        else:
            return render(request, 'customer/reg.html')
    else:
        pcode = request.POST.get('pcode')
        pnum = request.POST.get('pnum')
        if not pcode or not pnum:
            messages.error(request, '錯誤的病患代碼')
            return render(request, 'customer/reg.html')

        try:
            patient = PatientProfile.objects.filter(extend__join_code=pcode).get()
        except PatientProfile.DoesNotExist:
            messages.error(request, '錯誤的病患代碼')
            return render(request, 'customer/reg.html')
        except PatientProfile.MultipleObjectsReturned:
            messages.error(request, '衝突的病患代碼')
            return render(request, 'customer/reg.html')

        if request.POST.get('submit') == 'check':
            validate_code = get_random_string(8, allowed_chars='1234567890')
            request.session['pmatch'] = json.dumps((validate_code, patient.id))

            messages.info(request, '代碼已送出 (%s)' % validate_code)
            return render(request, 'customer/reg.html', {'confirm': True})
        else:
            validate_code, patient_id = json.loads(request.session.get('pmatch', '[]'))
            if request.POST.get('confirm-code') == validate_code:
                customer = CustomerProfile(name=pnum, phone=pnum)
                customer.save()
                Guardian(patient_id=patient_id, customer=customer, relation="未知的關係").save()
                LineBotIntegration(lineid=line_id, customer=customer).save()
                request.session.pop('pmatch')
                return redirect('patient_main')
            else:
                messages.error(request, '錯誤的驗證碼')
                return render(request, 'customer/reg.html', {'confirm': True})
