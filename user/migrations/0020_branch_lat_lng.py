from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0019_add_branch_and_rider_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='branch',
            name='latitude',
            field=models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='branch',
            name='longitude',
            field=models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True),
        ),
    ]
