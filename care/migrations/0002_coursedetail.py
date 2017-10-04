# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-10-03 07:40
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('care', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CourseDetail',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.TextField()),
                ('scheduled_at', models.TimeField()),
                ('table', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='care.Course')),
            ],
            options={
                'db_table': 'care_course_detail',
                'ordering': ['scheduled_at'],
            },
        ),
    ]
