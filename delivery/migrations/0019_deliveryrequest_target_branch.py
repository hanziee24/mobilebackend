from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0021_user_motorcycle_registration'),
        ('delivery', '0018_merge_20260428_0001'),
    ]

    operations = [
        migrations.AddField(
            model_name='deliveryrequest',
            name='target_branch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='delivery_requests', to='user.branch'),
        ),
    ]
