# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0003_rating'),
    ]

    operations = [
        migrations.AddField(
            model_name='delivery',
            name='sender_name',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AddField(
            model_name='delivery',
            name='sender_contact',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='delivery',
            name='receiver_name',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AddField(
            model_name='delivery',
            name='receiver_contact',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
