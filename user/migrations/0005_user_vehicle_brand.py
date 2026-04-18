# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0004_user_identity_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='vehicle_brand',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
