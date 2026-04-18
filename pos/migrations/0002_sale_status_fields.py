from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='status',
            field=models.CharField(choices=[('COMPLETED', 'Completed'), ('VOIDED', 'Voided'), ('REFUNDED', 'Refunded')], default='COMPLETED', max_length=20),
        ),
        migrations.AddField(
            model_name='sale',
            name='voided_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='sale',
            name='refunded_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
