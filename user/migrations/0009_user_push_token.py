# Generated migration file

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0008_alter_user_managers'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='push_token',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
