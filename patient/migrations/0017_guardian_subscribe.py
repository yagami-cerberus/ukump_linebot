# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-12-05 04:31
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patient', '0016_dummynote'),
    ]

    operations = [
        migrations.AddField(
            model_name='guardian',
            name='subscribe',
            field=models.BooleanField(default=True),
        ),
    ]
