from django.db import models
from user.models import User
from delivery.models import Delivery

class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('GCASH', 'GCash'),
        ('COD', 'Cash on Delivery'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    ]
    
    delivery = models.OneToOneField(Delivery, on_delete=models.CASCADE, related_name='payment')
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    
    # Transaction details
    transaction_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    
    # Receipt
    receipt_number = models.CharField(max_length=50, unique=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.receipt_number} - {self.payment_method} - ₱{self.amount}"


class RiderWallet(models.Model):
    rider = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.rider.get_full_name()} - ₱{self.balance}"


class WalletTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('EARNING', 'Earning'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('ADJUSTMENT', 'Adjustment'),
    ]
    
    wallet = models.ForeignKey(RiderWallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance_before = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Reference
    delivery = models.ForeignKey(Delivery, on_delete=models.SET_NULL, null=True, blank=True)
    withdrawal_request = models.ForeignKey('WithdrawalRequest', on_delete=models.SET_NULL, null=True, blank=True)
    
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.transaction_type} - ₱{self.amount}"


class WithdrawalRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('REJECTED', 'Rejected'),
    ]
    
    WITHDRAWAL_METHOD_CHOICES = [
        ('BANK', 'Bank Transfer'),
        ('GCASH', 'GCash'),
    ]
    
    rider = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawal_requests')
    wallet = models.ForeignKey(RiderWallet, on_delete=models.CASCADE)
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    withdrawal_method = models.CharField(max_length=20, choices=WITHDRAWAL_METHOD_CHOICES)
    
    # Account details
    account_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=100)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Admin notes
    admin_notes = models.TextField(blank=True, null=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_withdrawals')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.rider.get_full_name()} - ₱{self.amount} - {self.status}"
