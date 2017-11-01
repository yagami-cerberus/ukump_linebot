# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-10-31 06:18
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patient', '0009_ukumpglobal'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='caredairlyreport',
            name='report_version',
        ),
        migrations.AddField(
            model_name='caredairlyreport',
            name='catalog',
            field=models.TextField(default='dailyreport'),
            preserve_default=False,
        ),
    ]
