from user.models import User

try:
    user = User.objects.get(username='Ralphyy')
    print(f"Found user: {user.username}")
    print(f"User type: {user.user_type}")
    print(f"Is approved: {user.is_approved}")
    print(f"Email: {user.email}")
    
    # Reset password with proper hashing
    new_password = input("Enter new password for Ralphyy: ")
    user.set_password(new_password)
    user.save()
    
    print(f"Password updated successfully for {user.username}")
    print(f"You can now login with username: {user.username} and the new password")
    
except User.DoesNotExist:
    print("User 'Ralphyy' not found")
