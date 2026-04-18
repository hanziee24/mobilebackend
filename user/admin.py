from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, SupportTicket, Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ['name', 'address', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'address']


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'user_type', 'phone', 'branch', 'is_approved', 'is_active', 'date_joined']
    list_filter = ['user_type', 'is_active', 'is_approved', 'branch', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone']
    ordering = ['-date_joined']

    fieldsets = (
        ('Account Information', {'fields': ('username', 'password')}),
        ('Personal Information', {'fields': ('first_name', 'last_name', 'email', 'phone', 'date_of_birth', 'address')}),
        ('User Type & Role', {'fields': ('user_type', 'branch', 'is_approved', 'is_rejected', 'rejection_reason', 'vehicle_type', 'vehicle_brand', 'vehicle_plate', 'vehicle_color', 'license_number', 'is_available')}),
        ('Photo Verification', {'fields': ('identity_image', 'photo_front', 'photo_left', 'photo_right')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        ('Account Information', {'fields': ('username', 'password1', 'password2')}),
        ('Personal Information', {'fields': ('first_name', 'last_name', 'email', 'phone', 'address')}),
        ('User Type', {'fields': ('user_type', 'branch', 'vehicle_type', 'vehicle_brand', 'vehicle_plate', 'vehicle_color', 'license_number')}),
    )


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'email', 'concern_type', 'status', 'handled_by', 'created_at']
    list_filter = ['concern_type', 'status', 'created_at']
    search_fields = ['name', 'email', 'concern']
    ordering = ['-created_at']
