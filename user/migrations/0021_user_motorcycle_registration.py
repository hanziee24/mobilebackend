from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0020_branch_lat_lng'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='motorcycle_registration',
            field=models.ImageField(blank=True, null=True, upload_to='registrations/'),
        ),
    ]
