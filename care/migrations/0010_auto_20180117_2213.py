# Generated by Django 2.0.1 on 2018-01-17 14:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('care', '0009_auto_20171218_0858'),
    ]

    operations = [
        migrations.AlterField(
            model_name='course',
            name='report',
            field=models.CharField(blank=True, choices=[('care-1', '照護回報表'), ('comp-1', '陪伴回報表')], max_length=500, null=True),
        ),
    ]
