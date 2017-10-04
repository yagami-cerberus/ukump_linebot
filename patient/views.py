
from django.utils.dateparse import parse_date
from django.utils.timezone import now, localdate
from django.core.cache import cache
from django.shortcuts import render, redirect
from django.db.models import Q
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.urls import reverse
import json

from ukumpcore.linebot_utils import require_lineid
from ukumpcore import blackbox
from patient.models import (
    Profile as Patient,
    Manager as PatientManager,
    NursingSchedule,
    Guardian,
    CareDairlyReport,
    DEFAULT_REPORT_FORM)
from ukumpcore.linebot_utils import get_customer_id_from_lineid, get_employee_id_from_lineid  # get_employee_from_lineid, get_customer_from_lineid
from employee.models import Profile as Employee
from customer.models import Profile as Customer
from care.models import CourseDetail

TIME_12HR = 43200


@require_lineid
def dairy_schedule(request):
    line_id = request.session['line_id']
    if "pid" in request.GET:
        query = Patient.objects.filter(pk=request.GET['pid'])
    else:
        query = Patient.objects.get_queryset()

    date = localdate()
    employee_id = get_employee_id_from_lineid(line_id)
    cusomer_id = get_customer_id_from_lineid(line_id)

    pid = NursingSchedule.objects.today_schedule().filter(employee__linebotintegration__lineid=line_id).values_list('patient_id', flat=True)
    patients = query.filter(
        Q(guardian__customer_id=cusomer_id) |
        Q(manager__employee_id=employee_id, manager__relation="照護經理") |
        Q(id__in=pid))

    context = []
    for p in patients:
        ext = ('("weekly_mask" & %i > 0)' % (1 << date.isoweekday()), )
        courses = p.course_schedule.extra(where=ext)
        context.append((p, CourseDetail.objects.filter(table_id__in=courses.values_list('table_id', flat=True))))
    return render(request, 'patient/list_schedule.html', {"date": date, "patients": context})


@require_lineid
def summary(request, patient_id, catalog):
    pass


@require_lineid
def dairy_reports(request):
    line_id = request.session['line_id']
    cond = None

    employee_id = Employee.get_id_from_line_id(line_id)
    if employee_id:
        cond = (Q(id__in=PatientManager.objects.filter(employee_id=employee_id).values_list('patient_id', flat=True)) |
                Q(id__in=NursingSchedule.objects.today_schedule().filter(employee_id=employee_id).values_list('patient_id', flat=True)))

    customer_id = Customer.get_id_from_line_id(line_id)
    if customer_id:
        if cond:
            cond = cond | Q(id__in=Guardian.objects.filter(customer_id=customer_id).values_list('patient_id', flat=True))
        else:
            cond = Q(id__in=Guardian.objects.filter(customer_id=customer_id).values_list('patient_id', flat=True))

    if cond:
        patients = tuple(Patient.objects.filter(cond))
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
        employee_id = Employee.get_id_from_line_id(line_id)
        query = CareDairlyReport.objects.filter(patient_id=patient_id, report_date=report_date, report_period=report_period)

        if CareDairlyReport.is_manager(employee_id, patient_id):
            # Handle manager view
            report = query.first()
            if report:
                return render(request, 'patient/dairly_report_edit.html', {
                    'date': report_date,
                    'form': report.to_form(), 'patient': Patient.objects.get(pk=patient_id),
                    'mode': 'review' if (now() - report.updated_at).seconds < TIME_12HR or not report.reviewed_by_id else 'readonly',
                    'reviewed': report.reviewed_by_id is not None})

        if CareDairlyReport.is_nurse(employee_id, patient_id, report_date):
            report = query.first()
            if report:
                return render(request, 'patient/dairly_report_edit.html', {
                    'date': report_date,
                    'form': report.to_form(), 'patient': Patient.objects.get(pk=patient_id),
                    'mode': 'edit' if not report.reviewed_by and (now() - report.created_at).seconds < TIME_12HR else 'readonly'})
            elif report_date == localdate():
                return render(request, 'patient/dairly_report_edit.html', {
                    'date': report_date,
                    'form': DEFAULT_REPORT_FORM(), 'patient': Patient.objects.get(pk=patient_id),
                    'mode': 'edit'})
            else:
                raise Http404

        customer_id = Customer.get_id_from_line_id(line_id)
        if CareDairlyReport.is_guardian(customer_id, patient_id):
            # Handle customer view
            report = query.first()
            if report:
                return render(request, 'patient/dairly_report_edit.html', {
                    'date': report_date,
                    'form': report.to_form(), 'patient': Patient.objects.get(pk=patient_id),
                    'mode': 'readonly'})
        raise Http404

    @classmethod
    def post(cls, request, line_id, patient_id, report_date, report_period):
        query = CareDairlyReport.objects.filter(patient_id=patient_id, report_date=report_date, report_period=report_period)
        employee_id = Employee.get_id_from_line_id(line_id)

        if CareDairlyReport.is_manager(employee_id, patient_id):
            # Handle manager view
            report = query.first()
            if report:
                form = report.report_form(request.POST)
                if form.is_valid():
                    report.from_form(form)
                    report.reviewed_by_id = employee_id
                    report.save()
                    messages.info(request, '%s 審核已完成' % report.patient.name)
                    return redirect(reverse('patient_dairly_reports'))
                else:
                    messages.error(request, '欄位未填寫 %s' % form.errors)
                    return render(request, 'patient/dairly_report_edit.html', {
                        'date': report_date,
                        'form': form, 'patient': Patient.objects.get(pk=patient_id),
                        'mode': 'readonly'})

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
                            'form': form, 'patient': Patient.objects.get(pk=patient_id),
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
                        'form': form, 'patient': Patient.objects.get(pk=patient_id),
                        'mode': 'readonly'})
            raise Http404


@require_lineid
def list_members(request):
    if 'pid' in request.GET:
        query = Patient.objects.filter(pk=request.GET['pid'])
    else:
        query = Patient.objects.get_queryset()

    context = {}
    customer_id = get_customer_id_from_lineid(request.session['line_id'])
    if customer_id:
        context['managers'] = query.filter(guardian__customer_id=customer_id).distinct()
    employee_id = get_employee_id_from_lineid(request.session['line_id'])
    if customer_id:
        context['guardians'] = query.filter(manager__employee_id=employee_id, manager__relation="照護經理").distinct()
    return render(request, 'patient/list_members.html', context)


def dairy_card(request, card):
    if "HTTP_X_AMZN_TRACE_ID" in request.META:
        return redirect(request.build_absolute_uri(reverse('patient_card', args=(card,))) + "?token=" + request.GET['token'])

    c = cache.get('_patient_card:%s' % request.GET.get('token'))
    if not c:
        raise Http404

    session = json.loads(c)
    patient = Patient.objects.get(pk=session['p'])
    date = parse_date(session['d'])
    reports = patient.caredairlyreport_set.filter(report_date=date)
    img = blackbox.cards[int(card)](patient, date, reports)
    resp = HttpResponse(content_type="image/png")
    resp["Content-Disposition"] = "filename=\"card.png\""
    img.save(resp, "PNG")
    return resp
