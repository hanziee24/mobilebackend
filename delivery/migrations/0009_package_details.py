# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0008_delivery_is_fragile'),
    ]

    operations = [
        migrations.AddField(
            model_name='delivery',
            name='package_weight',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='delivery',
            name='package_length',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='delivery',
            name='package_width',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='delivery',
            name='package_height',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='delivery',
            name='package_photo',
            field=models.ImageField(blank=True, null=True, upload_to='packages/'),
        ),
        migrations.AddField(
            model_name='delivery',
            name='special_instructions',
            field=models.TextField(blank=True, null=True),
        ),
    ]
