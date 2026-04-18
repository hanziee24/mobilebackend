from django.contrib import admin
from .models import Payment, RiderWallet, WalletTransaction, WithdrawalRequest

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'customer', 'payment_method', 'amount', 'status', 'created_at']
    list_filter = ['payment_method', 'status', 'created_at']
    search_fields = ['receipt_number', 'customer__username', 'delivery__tracking_number']
    readonly_fields = ['created_at', 'paid_at']

@admin.register(RiderWallet)
class RiderWalletAdmin(admin.ModelAdmin):
    list_display = ['rider', 'balance', 'total_earned', 'total_withdrawn', 'updated_at']
    search_fields = ['rider__username', 'rider__first_name', 'rider__last_name']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ['wallet', 'transaction_type', 'amount', 'balance_after', 'created_at']
    list_filter = ['transaction_type', 'created_at']
    search_fields = ['wallet__rider__username', 'description']
    readonly_fields = ['created_at']

@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ['rider', 'amount', 'withdrawal_method', 'status', 'created_at']
    list_filter = ['withdrawal_method', 'status', 'created_at']
    search_fields = ['rider__username', 'account_name', 'account_number']
    readonly_fields = ['created_at', 'processed_at']
