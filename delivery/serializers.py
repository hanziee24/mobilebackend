from rest_framework import serializers
from urllib.parse import urlparse
from .models import Delivery, Notification, Rating, DeliveryRequest
from user.models import User


class BaseImageUrlSerializer(serializers.ModelSerializer):
    def _get_image_url(self, image_field):
        if not image_field:
            return None
        try:
            url = image_field.url if hasattr(image_field, 'url') else str(image_field)
        except Exception:
            url = str(image_field)

        if not url:
            return None

        parsed = urlparse(url)
        if parsed.scheme in ('http', 'https'):
            return url
        if url.startswith('//'):
            return f'https:{url}'

        if not url.startswith('/'):
            url = f'/{url}'

        request = self.context.get('request')
        if request:
            absolute_url = request.build_absolute_uri(url)
            forwarded_proto = request.META.get('HTTP_X_FORWARDED_PROTO', '')
            if forwarded_proto.lower() == 'https' and absolute_url.startswith('http://'):
                return absolute_url.replace('http://', 'https://', 1)
            return absolute_url
        return url

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

class DeliveryRequestSerializer(BaseImageUrlSerializer):
    customer_name = serializers.CharField(source='customer.get_full_name', read_only=True)
    package_photo = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = DeliveryRequest
        fields = ['id', 'customer_name', 'sender_name', 'sender_contact', 'sender_address',
                  'receiver_name', 'receiver_contact', 'receiver_address',
                  'item_type', 'weight', 'quantity', 'is_fragile', 'package_photo', 'special_instructions', 'preferred_payment_method', 'status', 'created_at']
        read_only_fields = ['id', 'status', 'created_at', 'customer_name']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['package_photo'] = self._get_image_url(instance.package_photo)
        return data

class DeliverySerializer(BaseImageUrlSerializer):
    rider_details = RiderSerializer(source='rider', read_only=True)
    customer_name = serializers.CharField(source='customer.get_full_name', read_only=True)
    receiver_phone = serializers.CharField(source='receiver_contact', read_only=True)
    has_rating = serializers.SerializerMethodField()
    package_photo = serializers.SerializerMethodField()
    proof_of_delivery = serializers.SerializerMethodField()
    
    class Meta:
        model = Delivery
        fields = '__all__'
        read_only_fields = ['tracking_number', 'created_at', 'updated_at', 'customer']
    
    def get_has_rating(self, obj):
        return hasattr(obj, 'rating')

    def get_package_photo(self, obj):
        return self._get_image_url(obj.package_photo)

    def get_proof_of_delivery(self, obj):
        return self._get_image_url(obj.proof_of_delivery)

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
