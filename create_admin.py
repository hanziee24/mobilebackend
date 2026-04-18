import os
import django
import sys

# Add the backend directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.contrib.auth.hashers import make_password
from user.models import User

# Create admin user
admin_user = User.objects.create(
    username='Alex',
    email='admin@deliverytrack.com',
    password=make_password('admin'),
    first_name='Alex',
    last_name='Administrator',
    phone='09123456789',
    address='Admin Office',
    user_type='ADMIN',
    is_staff=True,
    is_superuser=True,
    is_active=True
)

print("Admin user created successfully!")
print("Username: Alex")
print("Password: admin")
print("User Type: ADMIN")
