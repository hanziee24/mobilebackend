from rest_framework import serializers
from .models import Delivery, Notification, Rating, DeliveryRequest
from user.models import User

class RiderSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    branch_latitude = serializers.DecimalField(source='branch.latitude', max_digits=9, decimal_places=6, read_only=True)
    branch_longitude = serializers.DecimalField(source='branch.longitude', max_digits=9, decimal_places=6, read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'phone',
            'current_latitude',
            'current_longitude',
            'location_updated_at',
            'branch',
            'branch_name',
            'branch_latitude',
            'branch_longitude',
        ]

class DeliveryRequestSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.get_full_name', read_only=True)
    class Meta:
        model = DeliveryRequest
        fields = ['id', 'customer_name', 'sender_name', 'sender_contact', 'sender_address',
                  'receiver_name', 'receiver_contact', 'receiver_address',
                  'item_type', 'weight', 'quantity', 'is_fragile', 'special_instructions', 'preferred_payment_method', 'status', 'created_at']
        read_only_fields = ['id', 'status', 'created_at', 'customer_name']

class DeliverySerializer(serializers.ModelSerializer):
    rider_details = RiderSerializer(source='rider', read_only=True)
    customer_name = serializers.CharField(source='customer.get_full_name', read_only=True)
    receiver_phone = serializers.CharField(source='receiver_contact', read_only=True)
    has_rating = serializers.SerializerMethodField()
    
    class Meta:
        model = Delivery
        fields = '__all__'
        read_only_fields = ['tracking_number', 'created_at', 'updated_at', 'customer']
    
    def get_has_rating(self, obj):
        return hasattr(obj, 'rating')

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['created_at']

class RatingSerializer(serializers.ModelSerializer):
    delivery_tracking = serializers.CharField(source='delivery.tracking_number', read_only=True)
    rider_name = serializers.CharField(source='rider.get_full_name', read_only=True)
    customer_name = serializers.CharField(source='customer.get_full_name', read_only=True)
    
    class Meta:
        model = Rating
        fields = '__all__'
        read_only_fields = ['customer', 'rider', 'created_at']
    
    def validate_tip_amount(self, value):
        if value < 0:
            raise serializers.ValidationError('Tip amount cannot be negative')
        return value
