# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-11-30 06:34
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('patient', '0015_guardian_master'),
    ]

    operations = [
        migrations.CreateModel(
            name='DummyNote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.TextField()),
                ('message', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='patient.Profile')),
            ],
            options={
                'db_table': 'patient_note',
            },
        ),
    ]