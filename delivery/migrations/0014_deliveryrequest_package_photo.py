from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0013_deliveryrequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='deliveryrequest',
            name='package_photo',
            field=models.ImageField(blank=True, null=True, upload_to='packages/'),
        ),
    ]
