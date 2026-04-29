from rest_framework import serializers
import re
from urllib.parse import urlparse
from .models import User, SupportTicket, SavedAddress, Branch


def build_image_url(image_field, request=None):
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

    if request:
        absolute_url = request.build_absolute_uri(url)
        forwarded_proto = request.META.get('HTTP_X_FORWARDED_PROTO', '')
        if forwarded_proto.lower() == 'https' and absolute_url.startswith('http://'):
            return absolute_url.replace('http://', 'https://', 1)
        return absolute_url
    return url


class NullableAbsoluteImageField(serializers.ImageField):
    def to_internal_value(self, data):
        if data in ('', None, 'null'):
            return None
        return super().to_internal_value(data)

    def to_representation(self, value):
        request = self.context.get('request') if hasattr(self, 'context') else None
        return build_image_url(value, request)


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ['id', 'name', 'address', 'latitude', 'longitude', 'is_active']
        read_only_fields = ['id', 'is_active']


class UserSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    branch_address = serializers.CharField(source='branch.address', read_only=True)
    identity_image = serializers.SerializerMethodField()
    photo_front = serializers.SerializerMethodField()
    photo_left = serializers.SerializerMethodField()
    photo_right = serializers.SerializerMethodField()
    motorcycle_registration = serializers.SerializerMethodField()
    gcash_qr = NullableAbsoluteImageField(required=False, allow_null=True)

    def _get_image_url(self, image_field):
        return build_image_url(image_field, self.context.get('request'))

    def get_identity_image(self, obj):
        return self._get_image_url(obj.identity_image)

    def get_photo_front(self, obj):
        return self._get_image_url(obj.photo_front)

    def get_photo_left(self, obj):
        return self._get_image_url(obj.photo_left)

    def get_photo_right(self, obj):
        return self._get_image_url(obj.photo_right)

    def get_motorcycle_registration(self, obj):
        return self._get_image_url(obj.motorcycle_registration)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'user_type', 'is_approved', 'is_email_verified',
                  'is_rejected', 'rejection_reason', 'phone', 'date_of_birth', 'address', 'branch', 'branch_name', 'branch_address',
                  'vehicle_type', 'vehicle_brand', 'vehicle_plate', 'vehicle_color', 'license_number',
                  'motorcycle_registration', 'is_available', 'is_online', 'identity_image', 'photo_front', 'photo_left', 'photo_right',
                  'gcash_qr', 'created_at']
        read_only_fields = ['id', 'created_at', 'is_email_verified']

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    phone = serializers.CharField(required=True, max_length=15)
    address = serializers.CharField(required=True)
    user_type = serializers.ChoiceField(choices=['CUSTOMER', 'RIDER', 'CASHIER'], required=False, default='CUSTOMER')
    vehicle_brand = serializers.CharField(required=False, allow_blank=True, default='')
    vehicle_plate = serializers.CharField(required=False, allow_blank=True, default='')
    vehicle_color = serializers.CharField(required=False, allow_blank=True, default='')
    license_number = serializers.CharField(required=False, allow_blank=True, default='')


    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'first_name', 'last_name', 'user_type', 'phone', 'date_of_birth',
                  'address', 'vehicle_type', 'vehicle_brand', 'vehicle_plate', 'vehicle_color', 'license_number']

    def validate_username(self, value):
        if len(value) < 4:
            raise serializers.ValidationError('Username must be at least 4 characters.')
        if not re.match(r'^[a-zA-Z0-9_]+$', value):
            raise serializers.ValidationError('Username can only contain letters, numbers, and underscores.')
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('This username is already taken.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value.lower()

    def validate_phone(self, value):
        if not re.match(r'^(09|\+639)\d{9}$', value):
            raise serializers.ValidationError('Enter a valid PH mobile number (09XXXXXXXXX or +639XXXXXXXXX).')
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError('This phone number is already registered.')
        return value

    def validate_first_name(self, value):
        if not re.match(r"^[a-zA-Z\s''-]+$", value.strip()):
            raise serializers.ValidationError('First name must contain letters only.')
        return value.strip()

    def validate_last_name(self, value):
        if not re.match(r"^[a-zA-Z\s''-]+$", value.strip()):
            raise serializers.ValidationError('Last name must contain letters only.')
        return value.strip()

    def validate_password(self, value):
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError('Password must contain at least one uppercase letter.')
        if not re.search(r'[a-z]', value):
            raise serializers.ValidationError('Password must contain at least one lowercase letter.')
        if not re.search(r'[0-9]', value):
            raise serializers.ValidationError('Password must contain at least one number.')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            raise serializers.ValidationError('Password must contain at least one special character.')
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            user_type='CUSTOMER',
            phone=validated_data['phone'],
            date_of_birth=validated_data.get('date_of_birth'),
            address=validated_data['address'],
        )
        return user


class SavedAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedAddress
        fields = ['id', 'label', 'address', 'is_default', 'created_at']
        read_only_fields = ['id', 'created_at']


class SupportTicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = ['id', 'name', 'email', 'concern', 'concern_type', 'status', 'created_at']
        read_only_fields = ['id', 'status', 'created_at']

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError('Name must be at least 2 characters.')
        return value

    def validate_concern(self, value):
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError('Concern must be at least 10 characters.')
        return value


class SupportTicketSerializer(serializers.ModelSerializer):
    handled_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'name', 'email', 'concern', 'concern_type', 'status',
            'staff_notes', 'handled_by', 'handled_by_name',
            'resolved_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'handled_by_name', 'created_at', 'updated_at', 'resolved_at']

    def get_handled_by_name(self, obj):
        if not obj.handled_by:
            return None
        full_name = f'{obj.handled_by.first_name} {obj.handled_by.last_name}'.strip()
        return full_name or obj.handled_by.username


class SupportTicketUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicket
        fields = ['status', 'staff_notes']
