import os
import django
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from user.models import User

try:
    alex = User.objects.get(username='Alex')
    alex.user_type = 'ADMIN'
    alex.is_staff = True
    alex.is_superuser = True
    alex.save()
    print("SUCCESS: Updated Alex's user type to ADMIN")
    print(f"  Username: {alex.username}")
    print(f"  User Type: {alex.user_type}")
    print(f"  Is Staff: {alex.is_staff}")
    print(f"  Is Superuser: {alex.is_superuser}")
except User.DoesNotExist:
    print("ERROR: User 'Alex' not found in database")
except Exception as e:
    print(f"ERROR: {e}")
