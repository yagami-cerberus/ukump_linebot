# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-09-23 12:04
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('patient', '0003_auto_20170921_2242'),
    ]

    operations = [
        migrations.DeleteModel(
            name='GlobalVariable',
        ),
    ]
