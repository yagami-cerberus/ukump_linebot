# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-10-19 02:34
from __future__ import unicode_literals

import django.contrib.postgres.fields
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employee', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='members',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), blank=True, size=None),
        ),
        migrations.AlterField(
            model_name='profile',
            name='profile',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True),
        ),
    ]
