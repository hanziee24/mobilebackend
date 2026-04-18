from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0015_add_rejection_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='SupportTicket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('email', models.EmailField(max_length=254)),
                ('concern', models.TextField()),
                ('concern_type', models.CharField(choices=[('GENERAL', 'General'), ('RIDER_APPLICATION', 'Rider Application'), ('CASHIER_APPLICATION', 'Cashier Application')], default='GENERAL', max_length=30)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('IN_REVIEW', 'In Review'), ('RESOLVED', 'Resolved')], default='PENDING', max_length=20)),
                ('staff_notes', models.TextField(blank=True, null=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('handled_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='handled_support_tickets', to='user.user')),
                ('submitted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='submitted_support_tickets', to='user.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
