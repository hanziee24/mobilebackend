# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0007_delivery_time_slot'),
    ]

    operations = [
        migrations.AddField(
            model_name='delivery',
            name='is_fragile',
            field=models.BooleanField(default=False),
        ),
    ]
