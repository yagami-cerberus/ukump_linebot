# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-09-20 08:54
from __future__ import unicode_literals

import django.contrib.postgres.fields
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='LineBotIntegration',
            fields=[
                ('lineid', models.TextField(primary_key=True, serialize=False)),
            ],
            options={
                'db_table': 'employee_linebot_integration',
            },
        ),
        migrations.CreateModel(
            name='LineMessageQueue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField()),
                ('scheduled_at', models.DateTimeField()),
                ('queue_index', models.IntegerField(default=1)),
            ],
            options={
                'db_table': 'employee_line_message_queue',
            },
        ),
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.TextField()),
                ('profile', django.contrib.postgres.fields.jsonb.JSONField(null=True)),
                ('members', django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'employee',
            },
        ),
        migrations.AddField(
            model_name='linemessagequeue',
            name='employee',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='employee.Profile'),
        ),
        migrations.AddField(
            model_name='linebotintegration',
            name='employee',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='employee.Profile'),
        ),
    ]
