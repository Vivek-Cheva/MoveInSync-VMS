# Generated by Django 5.0 on 2025-04-09 16:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0002_visitrequest_reference_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='visitrequest',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('checked_in', 'Checked In'), ('completed', 'Completed')], default='pending', max_length=20),
        ),
    ]
