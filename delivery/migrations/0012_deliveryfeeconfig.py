from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0011_gcash_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeliveryFeeConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('base_fee', models.DecimalField(decimal_places=2, default=50, max_digits=10)),
                ('per_kg_rate', models.DecimalField(decimal_places=2, default=15, max_digits=10)),
                ('per_item_rate', models.DecimalField(decimal_places=2, default=10, max_digits=10)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
