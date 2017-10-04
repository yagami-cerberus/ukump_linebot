"""ukumpcore URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url
from django.contrib import admin

from ukumpcore.linebot_handler import linebot_handler
from ukumpcore import linelogin_handler
from patient import views as patient_view
from customer import views as customer_view

urlpatterns = [
    url(r'^kami/login/$', linelogin_handler.admin_login, name='line_association'),
    url(r'^kami/', admin.site.urls),

    url(r'^customer/association$', customer_view.line_association, name='line_association'),

    # 每日行程
    url(r'^patient/dairy_schedule$', patient_view.dairy_schedule, name='patient_main'),

    # 檢視/填寫日報表
    url(r'^patient/(?P<patient_id>[0-9]+)/summary/(?P<catalog>\d{1})/$', patient_view.summary, name='patient_summary'),

    # 檢視日報表清單
    url(r'^patient/dairy_reports$', patient_view.dairy_reports, name='patient_dairly_reports'),
    # 檢視/填寫日報表
    url(r'^patient/dairy_report/(?P<patient_id>[0-9]+)/(?P<date>\d{4}-\d{2}-\d{2})/(?P<period>\d{2})/$', patient_view.DairyReport, name='patient_dairly_report'),
    # 聯絡人清單
    url(r'^patient/members$', patient_view.list_members, name='patient_list_members'),
    # 卡片
    url(r'^patient/card/(?P<card>\d{1})/$', patient_view.dairy_card, name='patient_card'),


    url(r'^integrations/linebot$', linebot_handler),
    url(r'^integrations/linebot/nav/([a-z_-]{1,30})', linelogin_handler.nav, name='line_nav'),
    url(r'^integrations/linebot/login/final$', linelogin_handler.final, name='linelogin_final'),
    url(r'^integrations/linebot/login$', linelogin_handler.login, name='linelogin'),
]
