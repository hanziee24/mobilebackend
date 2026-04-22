from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0015_add_payment_fields_to_delivery'),
    ]

    operations = [
        migrations.AddField(
            model_name='deliveryrequest',
            name='preferred_payment_method',
            field=models.CharField(blank=True, default='CASH', max_length=20, null=True),
        ),
    ]
