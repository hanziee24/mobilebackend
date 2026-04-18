# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0006_delivery_delivery_attempts_delivery_max_attempts'),
    ]

    operations = [
        migrations.AddField(
            model_name='delivery',
            name='delivery_time_slot',
            field=models.CharField(blank=True, choices=[('MORNING', 'Morning (8AM-12PM)'), ('AFTERNOON', 'Afternoon (12PM-5PM)'), ('EVENING', 'Evening (5PM-8PM)'), ('ANYTIME', 'Anytime')], default='ANYTIME', max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='delivery',
            name='scheduled_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
