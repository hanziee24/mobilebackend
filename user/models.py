from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
import json

class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        # Set is_approved to False for riders and customers, True for admins
        if extra_fields.get('user_type') in ['RIDER', 'CUSTOMER', 'CASHIER']:
            extra_fields.setdefault('is_approved', False)
        else:
            extra_fields.setdefault('is_approved', True)
        if extra_fields.get('user_type') == 'ADMIN':
            extra_fields.setdefault('is_email_verified', True)
        else:
            extra_fields.setdefault('is_email_verified', False)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('user_type', 'ADMIN')
        extra_fields.setdefault('is_email_verified', True)
        return self.create_user(username, email, password, **extra_fields)

class User(AbstractUser):
    USER_TYPE_CHOICES = (
        ('CUSTOMER', 'Customer'),
        ('RIDER', 'Rider'),
        ('ADMIN', 'Admin'),
        ('CASHIER', 'Cashier'),
    )
    
    email = models.EmailField(unique=True)
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='CUSTOMER')
    is_approved = models.BooleanField(default=True)
    phone = models.CharField(max_length=15, blank=True, null=True, unique=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    identity_image = models.ImageField(upload_to='identity/', blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    
    # Rider specific fields
    branch = models.ForeignKey('Branch', on_delete=models.SET_NULL, null=True, blank=True, related_name='riders')
    vehicle_type = models.CharField(max_length=50, blank=True, null=True)
    vehicle_brand = models.CharField(max_length=100, blank=True, null=True)
    vehicle_plate = models.CharField(max_length=20, blank=True, null=True)
    vehicle_color = models.CharField(max_length=50, blank=True, null=True)
    license_number = models.CharField(max_length=50, blank=True, null=True)
    is_available = models.BooleanField(default=True)
    is_online = models.BooleanField(default=False)
    # Photo verification
    photo_front = models.ImageField(upload_to='rider_photos/', blank=True, null=True)
    photo_left = models.ImageField(upload_to='rider_photos/', blank=True, null=True)
    photo_right = models.ImageField(upload_to='rider_photos/', blank=True, null=True)

    # Email verification
    is_email_verified = models.BooleanField(default=False)
    email_verification_code = models.CharField(max_length=10, blank=True, null=True)
    email_verification_expires = models.DateTimeField(blank=True, null=True)

    # Rejection
    is_rejected = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True, null=True)
    
    # Location tracking
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)
    
    # GCash QR code (for cashiers)
    gcash_qr = models.ImageField(upload_to='gcash_qr/', blank=True, null=True)

    # Push notifications
    push_token = models.CharField(max_length=255, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='custom_user_set',
        blank=True
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='custom_user_set',
        blank=True
    )
    
    objects = UserManager()
    
    def __str__(self):
        return self.username


class PendingRegistration(models.Model):
    email = models.EmailField(unique=True)
    data = models.TextField()  # JSON blob of all registration fields
    image_name = models.CharField(max_length=255, blank=True, null=True)
    image_data = models.TextField(blank=True, null=True)  # base64 encoded image
    extra_data = models.TextField(blank=True, null=True, default='{}')  # JSON for extra photos
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def __str__(self):
        return f'PendingRegistration({self.email})'


class Branch(models.Model):
    name = models.CharField(max_length=100)
    address = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Branches'

    def __str__(self):
        return self.name


class SavedAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_addresses')
    label = models.CharField(max_length=100)  # e.g. Home, Work
    address = models.TextField()
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f'{self.user.username} - {self.label}'


class SupportTicket(models.Model):
    CONCERN_TYPE_CHOICES = (
        ('GENERAL', 'General'),
        ('RIDER_APPLICATION', 'Rider Application'),
        ('CASHIER_APPLICATION', 'Cashier Application'),
    )

    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('IN_REVIEW', 'In Review'),
        ('RESOLVED', 'Resolved'),
    )

    name = models.CharField(max_length=120)
    email = models.EmailField()
    concern = models.TextField()
    concern_type = models.CharField(max_length=30, choices=CONCERN_TYPE_CHOICES, default='GENERAL')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='submitted_support_tickets')
    handled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='handled_support_tickets')
    staff_notes = models.TextField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'SupportTicket({self.id}) {self.concern_type} - {self.email}'
