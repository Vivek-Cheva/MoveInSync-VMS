# Generated by Django 5.0 on 2025-04-10 02:49

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0003_visitrequest_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='visitrequest',
            name='scheduled_end',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='visitrequest',
            name='scheduled_start',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
