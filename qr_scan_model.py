# Add this to delivery/models.py

from django.db import models
from django.utils import timezone
from user.models import User

class QRScanLog(models.Model):
    """Audit trail for all QR code scans"""
    SCAN_TYPE_CHOICES = (
        ('PICKUP', 'Pickup Scan'),
        ('DELIVERY', 'Delivery Scan'),
        ('TRACKING', 'Tracking Scan'),
    )
    
    delivery = models.ForeignKey('Delivery', on_delete=models.CASCADE, related_name='scan_logs')
    scanned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    scan_type = models.CharField(max_length=20, choices=SCAN_TYPE_CHOICES)
    scanned_at = models.DateTimeField(default=timezone.now)
    
    # Location data
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_address = models.TextField(null=True, blank=True)
    
    # Status tracking
    status_before = models.CharField(max_length=50)
    status_after = models.CharField(max_length=50)
    
    # Device info
    device_info = models.CharField(max_length=255, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Validation
    is_valid = models.BooleanField(default=True)
    validation_error = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-scanned_at']
        indexes = [
            models.Index(fields=['delivery', '-scanned_at']),
            models.Index(fields=['scanned_by', '-scanned_at']),
        ]
    
    def __str__(self):
        return f"{self.scan_type} - {self.delivery.tracking_number} by {self.scanned_by}"
