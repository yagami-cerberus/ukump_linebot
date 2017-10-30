
from django.utils.dateparse import parse_date
from django.utils.timezone import now, localdate
from django.core.cache import cache
from django.shortcuts import render, redirect
from django.db.models import Q
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.conf import settings
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
from ukumpcore.linebot_utils import get_customer_id_from_lineid, get_employee_id_from_lineid, get_employee_from_lineid, get_customer_from_lineid
from ukumpcore.linebot_handler import flush_messages_queue
from ukumpcore.crm.agile import create_crm_ticket, get_patient_crm_url
from care.models import CourseDetail

TIME_12HR = 43200
EMERGENCY_TICKET_TEMPLATE = """通報人: %(reporter)s
緊急通報對象: <a href="%(patient_url)s">%(case_name)s</a>
通報聯絡電話: %(phone)s
緊急事項: %(event)s
處置: %(handle)s
備註: %(summary)s"""
EMERGENCY_REPLOY_EMPLOYEE_TEMPLATE = """案件 %(case_name)s 緊急通報！
通報人: %(reporter)s
通報聯絡電話: %(phone)s
緊急事項: %(event)s
處置: %(handle)s
備註: %(summary)s

CRM Ticket
%(ticket_url)s"""


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
    line_id = request.session['line_id']

    patient = Patient.objects.get(id=patient_id)

    if patient.guardian_set.filter(customer_id=get_customer_id_from_lineid(line_id)) or \
            patient.manager_set.filter(employee_id=get_employee_id_from_lineid(line_id)):

        members = {m.relation: m.employee.name for m in patient.manager_set.all()}
        members_list = ("照護經理", )

        return render(request, 'patient/summary_%s.html' % catalog, {
            "members": ((label, members[label]) for label in members_list if label in members),
            "patient": patient, "catalog": catalog,
            "last_report": patient.caredairlyreport_set.order_by("-report_date", "-report_period").first(),
        })
    else:
        raise Http404


@require_lineid
def dairy_reports(request):
    line_id = request.session['line_id']
    cond = None

    employee_id = get_employee_id_from_lineid(line_id)
    if employee_id:
        cond = (Q(id__in=PatientManager.objects.filter(employee_id=employee_id).values_list('patient_id', flat=True)) |
                Q(id__in=NursingSchedule.objects.today_schedule().filter(employee_id=employee_id).values_list('patient_id', flat=True)))

    customer_id = get_customer_id_from_lineid(line_id)
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
        employee_id = get_employee_id_from_lineid(line_id)
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

        customer_id = get_customer_id_from_lineid(line_id)
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
        employee_id = get_employee_id_from_lineid(line_id)

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
def emergency(request, patient_id):
    line_id = request.session['line_id']
    patient = Patient.objects.get(id=patient_id)
    employee = get_employee_from_lineid(line_id)
    customer = get_customer_from_lineid(line_id)

    source, role = None, None
    if patient.guardian_set.filter(customer=customer):
        source = customer
        role = "家屬"
    elif patient.manager_set.filter(employee=employee):
        source = employee
        role = "員工"
    elif patient.nursing_schedule.today_schedule().filter(employee=employee):
        source = employee
        role = "照護員"
    if not source:
        raise Http404

    if request.method == 'GET':
        return render(request, 'patient/emergency.html', {"patient": patient, "role": role, "source": source})
    elif request.method == 'POST':
        title = 'LINE 緊急通報案例 %s' % patient.name
        context = {
            'case_name': patient.name,
            'reporter': source.name,
            'phone': request.POST.get('phone'),
            'event': request.POST.get('event'),
            'handle': ', '.join(request.POST.getlist('handle')),
            'summary': request.POST.get('summary'),
            'patient_url': get_patient_crm_url(patient)
        }

        ticket_id, ticket_url = create_crm_ticket(source, title, EMERGENCY_TICKET_TEMPLATE % context, emergency=True)

        context['ticket_url'] = ticket_url
        source.push_message("通報案件代碼 #%s\n\n照護經理與關懷中心已收到您針對 %s 所送出的緊急通報，必要時請直接聯繫照護經理。" % (ticket_id, patient.name))
        for member in patient.managers.filter(manager__relation="照護經理"):
            member.push_message(EMERGENCY_REPLOY_EMPLOYEE_TEMPLATE % context)
        flush_messages_queue()
        return redirect(settings.LINEBOT_URI)


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
    c = json.dumps({'p': 1, 'd': '2017-10-19'})
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
