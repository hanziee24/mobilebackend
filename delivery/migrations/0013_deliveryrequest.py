from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0012_deliveryfeeconfig'),
        ('user', '0020_branch_lat_lng'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeliveryRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sender_name', models.CharField(max_length=200)),
                ('sender_contact', models.CharField(max_length=20)),
                ('sender_address', models.TextField()),
                ('receiver_name', models.CharField(max_length=200)),
                ('receiver_contact', models.CharField(max_length=20)),
                ('receiver_address', models.TextField()),
                ('item_type', models.CharField(max_length=200)),
                ('weight', models.CharField(max_length=20)),
                ('quantity', models.CharField(max_length=20)),
                ('is_fragile', models.BooleanField(default=False)),
                ('special_instructions', models.TextField(blank=True, null=True)),
                ('status', models.CharField(max_length=20, choices=[('PENDING', 'Pending'), ('ACCEPTED', 'Accepted'), ('CANCELLED', 'Cancelled')], default='PENDING')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='delivery_requests', to='user.user')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
