import os
import django
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from user.models import User

try:
    ralph = User.objects.get(username='Ralph')
    print(f"Username: {ralph.username}")
    print(f"User Type: {ralph.user_type}")
    print(f"Is Staff: {ralph.is_staff}")
    print(f"Is Active: {ralph.is_active}")
    
    if ralph.user_type != 'RIDER':
        print(f"\nFixing Ralph's user type from {ralph.user_type} to RIDER...")
        ralph.user_type = 'RIDER'
        ralph.save()
        print("SUCCESS: Ralph is now a RIDER")
    else:
        print("\nRalph is already a RIDER")
        
except User.DoesNotExist:
    print("ERROR: User 'Ralph' not found in database")
except Exception as e:
    print(f"ERROR: {e}")
