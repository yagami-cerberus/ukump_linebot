# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-11-12 14:17
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('care', '0004_auto_20171016_1049'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='report',
            field=models.CharField(blank=True, choices=[('照護回報表', '照護回報表'), ('陪伴回報表', '陪伴回報表')], max_length=500, null=True),
        ),
    ]