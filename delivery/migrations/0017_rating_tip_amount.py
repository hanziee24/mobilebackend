from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0016_deliveryrequest_preferred_payment_method'),
    ]

    operations = [
        migrations.AddField(
            model_name='rating',
            name='tip_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
