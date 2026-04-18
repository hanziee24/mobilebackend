# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0003_user_current_latitude_user_current_longitude_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='identity_image',
            field=models.ImageField(blank=True, null=True, upload_to='identity/'),
        ),
    ]
