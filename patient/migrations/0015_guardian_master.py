# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-11-25 06:00
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patient', '0014_auto_20171112_2302'),
    ]

    operations = [
        migrations.AddField(
            model_name='guardian',
            name='master',
            field=models.BooleanField(default=False),
        ),
    ]
