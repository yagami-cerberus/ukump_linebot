
from django.shortcuts import render, redirect
from django.utils.dateparse import parse_date
from django.utils.timezone import now, localdate
from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.urls import reverse

from ukumpcore.line_utils import require_lineid
from patient.models import (
    Profile as PatientProfile,
    NursingSchedule,
    CareDairlyReport,
    DEFAULT_REPORT_FORM)
from employee.models import Profile as EmployeeProfile
from customer.models import Profile as CustomerProfile

TIME_12HR = 43200


@require_lineid
def dairy_schedule(request):
    line_id = request.session['line_id']

    pid = NursingSchedule.objects.today_schedule().filter(employee__linebotintegration__lineid=line_id).values_list('patient_id', flat=True)
    patients = PatientProfile.objects.filter(
        Q(guardian__customer__linebotintegration__lineid=line_id) |
        Q(manager__employee__linebotintegration__lineid=line_id) |
        Q(id__in=pid))

    return render(request, 'patient/list_schedule.html', {"patients": patients})


@require_lineid
def dairy_reports(request):
    line_id = request.session['line_id']
    cond = None

    employee_id = EmployeeProfile.get_id_from_line_id(line_id)
    if employee_id:
        pid = NursingSchedule.objects.today_schedule().filter(employee_id=employee_id).values_list('patient_id', flat=True)
        cond = Q(manager__employee_id=employee_id) | Q(id__in=pid)

    customer_id = CustomerProfile.get_id_from_line_id(line_id)
    if customer_id:
        if cond:
            cond = cond | Q(guardian__customer_id=customer_id)
        else:
            cond = Q(guardian__customer_id=customer_id)

    if cond:
        patients = tuple(PatientProfile.objects.filter(cond))
    else:
        patients = ()

    return render(request, 'patient/list_reports.html', {"patients": patients})


@require_lineid
class DairyReport(object):
    def __new__(cls, request, patient_id, date, period):
        line_id = request.session['line_id']
        if period not in ('12', '18'):
            raise Http404
        if request.method == 'GET':
            return cls.get(request, line_id, patient_id, parse_date(date), int(period))
        elif request.method == 'POST':
            return cls.post(request, line_id, patient_id, parse_date(date), int(period))
        else:
            raise Http404

    @classmethod
    def get(cls, request, line_id, patient_id, report_date, report_period):
        employee_id = EmployeeProfile.get_id_from_line_id(line_id)
        query = CareDairlyReport.objects.filter(patient_id=patient_id, report_date=report_date, report_period=report_period)

        if CareDairlyReport.is_manager(employee_id, patient_id):
            # Handle manager view
            report = query.first()
            if report:
                return render(request, 'patient/dairly_report_edit.html', {
                    'date': report_date,
                    'form': report.to_form(), 'patient': PatientProfile.objects.get(pk=patient_id),
                    'mode': 'review' if (now() - report.updated_at).seconds < TIME_12HR or not report.reviewed_by_id else 'readonly',
                    'reviewed': report.reviewed_by_id is not None})

        if CareDairlyReport.is_nurse(employee_id, patient_id, report_date):
            report = query.first()
            if report:
                return render(request, 'patient/dairly_report_edit.html', {
                    'date': report_date,
                    'form': report.to_form(), 'patient': PatientProfile.objects.get(pk=patient_id),
                    'mode': 'edit' if not report.reviewed_by and (now() - report.created_at).seconds < TIME_12HR else 'readonly'})
            elif report_date == localdate():
                return render(request, 'patient/dairly_report_edit.html', {
                    'date': report_date,
                    'form': DEFAULT_REPORT_FORM(), 'patient': PatientProfile.objects.get(pk=patient_id),
                    'mode': 'edit'})
            else:
                raise Http404

        customer_id = CustomerProfile.get_id_from_line_id(line_id)
        if CareDairlyReport.is_guardian(customer_id, patient_id):
            # Handle customer view
            report = query.first()
            if report:
                return render(request, 'patient/dairly_report_edit.html', {
                    'date': report_date,
                    'form': report.to_form(), 'patient': PatientProfile.objects.get(pk=patient_id),
                    'mode': 'readonly'})
        raise Http404

    @classmethod
    def post(cls, request, line_id, patient_id, report_date, report_period):
        query = CareDairlyReport.objects.filter(patient_id=patient_id, report_date=report_date, report_period=report_period)
        employee_id = EmployeeProfile.get_id_from_line_id(line_id)

        if CareDairlyReport.is_manager(employee_id, patient_id):
            # Handle manager view
            report = query.first()
            if report and report.reviewed_by_id is None:
                report.reviewed_by_id = employee_id
                report.save()
                messages.info(request, '%s 審核已完成' % report.patient.name)
                return redirect(reverse('patient_dairly_reports'))

        if CareDairlyReport.is_nurse(employee_id, patient_id, report_date):
            report = query.first()
            if report:
                if report.reviewed_by_id:
                    messages.info(request, '%s 已審核完成' % report.patient.name)
                    return redirect(reverse('patient_dairly_reports'))
                else:
                    form = report.report_form(request.POST)
                    if form.is_valid():
                        report.from_form(form)
                        report.filled_by_id = employee_id
                        report.save()
                        messages.info(request, '%s 已提交' % report.patient.name)
                        return redirect(reverse('patient_dairly_reports'))
                    else:
                        messages.error(request, '欄位未填寫 %s' % form.errors)
                        return render(request, 'patient/dairly_report_edit.html', {
                            'date': report_date,
                            'form': form, 'patient': PatientProfile.objects.get(pk=patient_id),
                            'mode': 'readonly'})
            else:
                form = DEFAULT_REPORT_FORM(request.POST)
                if form.is_valid():
                    report = CareDairlyReport(patient_id=patient_id, report_date=report_date, report_period=report_period, filled_by_id=employee_id)
                    report.from_form(form)
                    report.save()
                    messages.info(request, '%s 已提交' % report.patient.name)
                    return redirect(reverse('patient_dairly_reports'))
                else:
                    messages.error(request, '欄位未填寫 %s' % form.errors)
                    return render(request, 'patient/dairly_report_edit.html', {
                        'date': report_date,
                        'form': form, 'patient': PatientProfile.objects.get(pk=patient_id),
                        'mode': 'readonly'})
            raise Http404
