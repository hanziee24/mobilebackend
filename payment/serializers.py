from rest_framework import serializers
from .models import Payment, RiderWallet, WalletTransaction

class PaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    delivery_tracking = serializers.SerializerMethodField()
    
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ['customer', 'receipt_number', 'created_at', 'paid_at']
    
    def get_customer_name(self, obj):
        return obj.customer.get_full_name()
    
    def get_delivery_tracking(self, obj):
        return obj.delivery.tracking_number


class RiderWalletSerializer(serializers.ModelSerializer):
    rider_name = serializers.SerializerMethodField()
    
    class Meta:
        model = RiderWallet
        fields = '__all__'
        read_only_fields = ['rider', 'balance', 'total_earned', 'total_withdrawn', 'created_at', 'updated_at']
    
    def get_rider_name(self, obj):
        return obj.rider.get_full_name()


class WalletTransactionSerializer(serializers.ModelSerializer):
    delivery = serializers.SerializerMethodField()
    delivery_tracking = serializers.SerializerMethodField()
    
    class Meta:
        model = WalletTransaction
        fields = '__all__'
        read_only_fields = ['wallet', 'created_at']

    def get_delivery(self, obj):
        if not obj.delivery:
            return None
        return {
            'id': obj.delivery.id,
            'tracking_number': obj.delivery.tracking_number,
        }
    
    def get_delivery_tracking(self, obj):
        return obj.delivery.tracking_number if obj.delivery else None
