# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-11-12 15:02
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patient', '0013_caredailyreport_token'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='caredailyreport',
            name='catalog',
        ),
        migrations.RemoveField(
            model_name='caredailyreport',
            name='token',
        ),
        migrations.AddField(
            model_name='caredailyreport',
            name='form_id',
            field=models.TextField(blank=True, null=True),
        ),
    ]
