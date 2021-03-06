# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-09-20 16:50
from __future__ import unicode_literals

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('employee', '0001_initial'),
        ('patient', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CareDairlyReport',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_date', models.DateField()),
                ('report_period', models.IntegerField()),
                ('report_version', models.IntegerField(default=1)),
                ('report', django.contrib.postgres.fields.jsonb.JSONField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('filled_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='employee.Profile')),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='patient.Profile')),
                ('reviewed_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='employee.Profile')),
            ],
            options={
                'db_table': 'patient_dairly_report',
            },
        ),
        migrations.AlterField(
            model_name='nursingschedule',
            name='patient',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='nursing_schedule', to='patient.Profile'),
        ),
    ]
