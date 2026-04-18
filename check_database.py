import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.db import connection
from user.models import User

def check_and_fix_database():
    print("=" * 50)
    print("Checking Database Status")
    print("=" * 50)
    
    # Check if is_online column exists
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(user_user)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        print(f"\nFound {len(column_names)} columns in user_user table")
        
        if 'is_online' in column_names:
            print("✓ is_online column exists")
            
            # Count riders
            total_riders = User.objects.filter(user_type='RIDER').count()
            online_riders = User.objects.filter(user_type='RIDER', is_online=True).count()
            
            print(f"\nRider Status:")
            print(f"  Total Riders: {total_riders}")
            print(f"  Online: {online_riders}")
            print(f"  Offline: {total_riders - online_riders}")
            
        else:
            print("✗ is_online column MISSING!")
            print("\nAdding is_online column...")
            
            try:
                cursor.execute("ALTER TABLE user_user ADD COLUMN is_online BOOLEAN DEFAULT 0")
                print("✓ is_online column added successfully")
                
                # Set all riders to offline
                User.objects.filter(user_type='RIDER').update(is_online=False)
                print("✓ All riders set to offline")
                
            except Exception as e:
                print(f"✗ Error adding column: {e}")
                return False
    
    print("\n" + "=" * 50)
    print("Database check complete!")
    print("=" * 50)
    return True

if __name__ == '__main__':
    check_and_fix_database()
