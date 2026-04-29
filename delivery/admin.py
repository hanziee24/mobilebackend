from django.contrib import admin
from django.utils.html import format_html
from .models import Delivery, Notification, Rating, DeliveryRequest

@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = [
        'tracking_number', 'sender_name', 'receiver_name', 'delivery_address_short',
        'delivery_fee', 'status_badge', 'is_approved', 'is_fragile', 'rider', 'created_at'
    ]
    list_filter = ['status', 'is_approved', 'is_fragile', 'created_at']
    search_fields = [
        'tracking_number', 'sender_name', 'sender_contact',
        'receiver_name', 'receiver_contact', 'delivery_address',
        'customer__username', 'rider__username'
    ]
    readonly_fields = ['tracking_number', 'created_at', 'updated_at', 'gcash_proof_preview']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    list_per_page = 25

    fieldsets = (
        ('Tracking', {
            'fields': ('tracking_number', 'status', 'is_approved', 'progress', 'estimated_time')
        }),
        ('Sender', {
            'fields': ('customer', 'sender_name', 'sender_contact', 'pickup_address')
        }),
        ('Receiver', {
            'fields': ('receiver_name', 'receiver_contact', 'delivery_address', 'delivery_time_slot', 'scheduled_date')
        }),
        ('Package', {
            'fields': ('is_fragile', 'package_weight', 'package_length', 'package_width', 'package_height', 'package_photo', 'special_instructions')
        }),
        ('Payment', {
            'fields': ('delivery_fee', 'gcash_name', 'gcash_number', 'gcash_proof_preview')
        }),
        ('Delivery', {
            'fields': ('rider', 'proof_of_delivery', 'notes', 'failure_reason', 'delivery_attempts', 'max_attempts')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def delivery_address_short(self, obj):
        addr = (obj.delivery_address or '').split('|')[0].strip()
        return addr[:40] + '...' if len(addr) > 40 else addr
    delivery_address_short.short_description = 'Delivery Address'

    def status_badge(self, obj):
        colors = {
            'PENDING': '#FF9800', 'PICKED_UP': '#1565C0', 'IN_TRANSIT': '#1565C0',
            'OUT_FOR_DELIVERY': '#7B1FA2', 'DELIVERED': '#2E7D32',
            'CANCELLED': '#C62828', 'FAILED': '#C62828',
        }
        color = colors.get(obj.status, '#999')
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:bold">{}</span>',
            color, obj.status.replace('_', ' ')
        )
    status_badge.short_description = 'Status'

    def gcash_proof_preview(self, obj):
        if obj.gcash_proof:
            return format_html('<img src="{}" style="max-height:200px;border-radius:8px" />', obj.gcash_proof.url)
        return '—'
    gcash_proof_preview.short_description = 'GCash Proof'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'is_read', 'created_at']
    list_filter = ['is_read', 'created_at']
    search_fields = ['user__username', 'title', 'message']

@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ['customer', 'rider', 'rating', 'delivery', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['customer__username', 'rider__username', 'delivery__tracking_number']


@admin.register(DeliveryRequest)
class DeliveryRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'customer', 'sender_name', 'receiver_name', 'target_branch',
        'preferred_payment_method', 'status_badge', 'is_fragile', 'created_at'
    ]
    list_filter = ['status', 'is_fragile', 'preferred_payment_method', 'target_branch', 'created_at']
    search_fields = [
        'customer__username', 'customer__first_name', 'customer__last_name',
        'sender_name', 'sender_contact', 'receiver_name', 'receiver_contact',
        'sender_address', 'receiver_address', 'item_type'
    ]
    readonly_fields = ['created_at', 'package_photo_preview']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    list_per_page = 25

    fieldsets = (
        ('Request Info', {
            'fields': ('customer', 'status', 'target_branch', 'created_at')
        }),
        ('Sender', {
            'fields': ('sender_name', 'sender_contact', 'sender_address')
        }),
        ('Receiver', {
            'fields': ('receiver_name', 'receiver_contact', 'receiver_address')
        }),
        ('Parcel', {
            'fields': (
                'item_type', 'weight', 'quantity', 'is_fragile',
                'special_instructions', 'package_photo', 'package_photo_preview'
            )
        }),
        ('Payment', {
            'fields': ('preferred_payment_method',)
        }),
    )

    def status_badge(self, obj):
        colors = {
            'PENDING': '#FF9800',
            'ACCEPTED': '#2E7D32',
            'CANCELLED': '#C62828',
        }
        color = colors.get(obj.status, '#999')
        return format_html(
            '<span style="background:{};color:#fff;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:bold">{}</span>',
            color, obj.status.replace('_', ' ')
        )
    status_badge.short_description = 'Status'

    def package_photo_preview(self, obj):
        if obj.package_photo:
            return format_html('<img src="{}" style="max-height:200px;border-radius:8px" />', obj.package_photo.url)
        return '—'
    package_photo_preview.short_description = 'Package Photo Preview'
