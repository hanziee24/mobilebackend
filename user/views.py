from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import random
import json
from .models import User, PendingRegistration, SupportTicket, SavedAddress, Branch
from .serializers import (
    UserSerializer,
    RegisterSerializer,
    BranchSerializer,
    SavedAddressSerializer,
    SupportTicketCreateSerializer,
    SupportTicketSerializer,
    SupportTicketUpdateSerializer,
)
from .email_utils import send_system_email

PENDING_REG_TIMEOUT = 600  # 10 minutes

def _generate_verification_code():
    return f"{random.randint(0, 999999):06d}"


def _mail_error_response(message: str, exc: Exception):
    if settings.DEBUG:
        return Response(
            {'error': f'{message} ({exc})'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return Response({'error': message}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _send_otp_email(email: str, code: str):
    subject = 'Your JRNZ Tracking Express verification code'
    message = (
        f'Your verification code is {code}.\n\n'
        'This code expires in 10 minutes.'
    )
    send_system_email(
        subject,
        message,
        [email],
        fail_silently=False,
    )

def _send_verification_email(user: User):
    code = _generate_verification_code()
    user.email_verification_code = code
    user.email_verification_expires = timezone.now() + timedelta(minutes=10)
    user.is_email_verified = False
    user.save(update_fields=['email_verification_code', 'email_verification_expires', 'is_email_verified'])
    _send_otp_email(user.email, code)


def _is_staff_ticket_manager(user):
    return user.is_authenticated and user.user_type in ['ADMIN', 'CASHIER']

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def get_branches(request):
    if request.method == 'POST':
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
        serializer = BranchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    branches = Branch.objects.filter(is_active=True)
    return Response(BranchSerializer(branches, many=True).data)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def branch_detail(request, branch_id):
    if request.user.user_type != 'ADMIN':
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
    try:
        branch = Branch.objects.get(id=branch_id)
    except Branch.DoesNotExist:
        return Response({'error': 'Branch not found'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'DELETE':
        branch.is_active = False
        branch.save(update_fields=['is_active'])
        return Response({'message': 'Branch deactivated'})
    serializer = BranchSerializer(branch, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save()
    return Response(serializer.data)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def saved_addresses(request):
    if request.method == 'GET':
        addresses = SavedAddress.objects.filter(user=request.user)
        return Response(SavedAddressSerializer(addresses, many=True).data)

    serializer = SavedAddressSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if serializer.validated_data.get('is_default'):
        SavedAddress.objects.filter(user=request.user, is_default=True).update(is_default=False)

    serializer.save(user=request.user)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def saved_address_detail(request, address_id):
    try:
        address = SavedAddress.objects.get(id=address_id, user=request.user)
    except SavedAddress.DoesNotExist:
        return Response({'error': 'Address not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'DELETE':
        address.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = SavedAddressSerializer(address, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if serializer.validated_data.get('is_default'):
        SavedAddress.objects.filter(user=request.user, is_default=True).update(is_default=False)

    serializer.save()
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def nearest_hub(request):
    import math
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    try:
        lat = float(request.query_params.get('lat', ''))
        lng = float(request.query_params.get('lng', ''))
    except (TypeError, ValueError):
        return Response({'error': 'lat and lng are required'}, status=status.HTTP_400_BAD_REQUEST)
    branches = Branch.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False)
    results = []
    for b in branches:
        dist = haversine(lat, lng, float(b.latitude), float(b.longitude))
        results.append({**BranchSerializer(b).data, 'distance_km': round(dist, 2)})
    results.sort(key=lambda x: x['distance_km'])
    return Response(results)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_phone(request):
    phone = (request.query_params.get('phone') or '').strip()
    if not phone:
        return Response({'exists': False})
    try:
        customer = User.objects.get(phone=phone, user_type='CUSTOMER')
        return Response({
            'exists': True,
            'full_name': customer.get_full_name() or customer.username,
            'address': customer.address or '',
        })
    except User.DoesNotExist:
        return Response({'exists': False})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_staff(request):
    if request.user.user_type != 'ADMIN':
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)

    user_type = request.data.get('user_type', '').upper()
    if user_type not in ['RIDER', 'CASHIER']:
        return Response({'error': 'user_type must be RIDER or CASHIER'}, status=status.HTTP_400_BAD_REQUEST)

    required = ['username', 'email', 'password', 'first_name', 'last_name', 'phone', 'address', 'date_of_birth']
    for field in required:
        if not request.data.get(field, '').strip():
            return Response({'error': f'{field} is required'}, status=status.HTTP_400_BAD_REQUEST)

    if user_type == 'RIDER':
        for field in ['vehicle_type', 'vehicle_brand', 'license_number']:
            if not request.data.get(field, '').strip():
                return Response({'error': f'{field} is required for riders'}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(username__iexact=request.data['username']).exists():
        return Response({'error': 'Username already taken'}, status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(email__iexact=request.data['email']).exists():
        return Response({'error': 'Email already registered'}, status=status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(phone=request.data['phone']).exists():
        return Response({'error': 'Phone number already registered'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.create_user(
            username=request.data['username'].strip(),
            email=request.data['email'].strip().lower(),
            password=request.data['password'],
            first_name=request.data['first_name'].strip(),
            last_name=request.data['last_name'].strip(),
            phone=request.data['phone'].strip(),
            address=request.data['address'].strip(),
            date_of_birth=request.data.get('date_of_birth') or None,
            user_type=user_type,
            vehicle_type=request.data.get('vehicle_type', '').strip(),
            vehicle_brand=request.data.get('vehicle_brand', '').strip(),
            license_number=request.data.get('license_number', '').strip(),
            is_approved=True,
            is_email_verified=True,
        )

        # Send credentials email to the new staff member
        role_label = 'Rider' if user_type == 'RIDER' else 'Cashier'
        try:
            send_system_email(
                subject=f'Your JRNZ Tracking Express {role_label} Account',
                message=(
                    f'Hi {user.first_name},\n\n'
                    f'Your {role_label} account has been created by the admin.\n\n'
                    f'Here are your login credentials:\n'
                    f'  Username : {user.username}\n'
                    f'  Password : {request.data["password"]}\n\n'
                    f'Please login to the JRNZ Tracking Express app and change your password after your first login.\n\n'
                    f'JRNZ Tracking Express Team'
                ),
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f'Failed to send credentials email: {e}')

        return Response({
            'message': f'{role_label} account created successfully. Login credentials sent to {user.email}.',
            'username': user.username,
            'email': user.email,
            'user_type': user.user_type,
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    validated = serializer.validated_data
    email = validated['email']
    user_type = validated.get('user_type', 'CUSTOMER').upper()

    # Rider-specific field validation
    if user_type == 'RIDER':
        for field in ['vehicle_brand', 'vehicle_plate', 'vehicle_color', 'license_number']:
            if not validated.get(field, '').strip():
                return Response({'error': f'{field} is required for riders.'}, status=status.HTTP_400_BAD_REQUEST)
    code = _generate_verification_code()
    expires_at = timezone.now() + timedelta(minutes=10)

    payload = {
        'username': validated['username'],
        'password': validated['password'],
        'first_name': validated['first_name'],
        'last_name': validated['last_name'],
        'user_type': user_type,
        'phone': validated['phone'],
        'address': validated['address'],
        'date_of_birth': str(validated['date_of_birth']) if validated.get('date_of_birth') else None,
        'vehicle_brand': validated.get('vehicle_brand', ''),
        'vehicle_plate': validated.get('vehicle_plate', ''),
        'vehicle_color': validated.get('vehicle_color', ''),
        'license_number': validated.get('license_number', ''),
        'branch_id': None,
    }

    # Handle identity image + 3 verification photos for riders
    image_name = None
    image_data = None
    extra_images = {}
    if user_type == 'RIDER':
        import base64
        if 'identity_image' in request.FILES:
            img = request.FILES['identity_image']
            image_name = img.name
            image_data = base64.b64encode(img.read()).decode('utf-8')
        for photo_field in ['photo_front', 'photo_left', 'photo_right', 'motorcycle_registration']:
            if photo_field in request.FILES:
                f = request.FILES[photo_field]
                extra_images[photo_field] = {
                    'name': f.name,
                    'data': base64.b64encode(f.read()).decode('utf-8'),
                }

    PendingRegistration.objects.update_or_create(
        email=email,
        defaults={
            'data': json.dumps(payload),
            'image_name': image_name,
            'image_data': image_data,
            'code': code,
            'expires_at': expires_at,
            'extra_data': json.dumps(extra_images) if extra_images else '{}',
        }
    )

    try:
        _send_otp_email(email, code)
    except Exception as e:
        print(f"Email send error: {e}")
        PendingRegistration.objects.filter(email=email).delete()
        return _mail_error_response('Failed to send verification email. Please try again.', e)

    return Response({'message': 'Verification code sent. Please check your email.'}, status=status.HTTP_200_OK)

class UserProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    authentication_classes = [JWTAuthentication]
    
    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        try:
            # Handle location updates
            if 'current_latitude' in request.data or 'current_longitude' in request.data:
                user = self.get_object()
                user.current_latitude = request.data.get('current_latitude', user.current_latitude)
                user.current_longitude = request.data.get('current_longitude', user.current_longitude)
                user.location_updated_at = timezone.now()
                user.save()
                serializer = self.get_serializer(user)
                return Response(serializer.data)
            
            # Handle is_online updates
            if 'is_online' in request.data:
                user = self.get_object()
                if user.user_type == 'RIDER':
                    user.is_online = request.data.get('is_online', False)
                    user.save(update_fields=['is_online'])
                    serializer = self.get_serializer(user)
                    return Response(serializer.data)
            
            return super().update(request, *args, **kwargs)
        except Exception as e:
            print(f"Profile update error: {e}")
            return Response({'error': 'Failed to update profile'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def partial_update(self, request, *args, **kwargs):
        try:
            # Handle location updates
            if 'current_latitude' in request.data or 'current_longitude' in request.data:
                user = self.get_object()
                user.current_latitude = request.data.get('current_latitude', user.current_latitude)
                user.current_longitude = request.data.get('current_longitude', user.current_longitude)
                user.location_updated_at = timezone.now()
                user.save()
                serializer = self.get_serializer(user)
                return Response(serializer.data)
            
            # Handle is_online updates
            if 'is_online' in request.data:
                user = self.get_object()
                if user.user_type == 'RIDER':
                    user.is_online = request.data.get('is_online', False)
                    user.save(update_fields=['is_online'])
                    serializer = self.get_serializer(user)
                    return Response(serializer.data)
            
            return super().partial_update(request, *args, **kwargs)
        except Exception as e:
            print(f"Profile partial update error: {e}")
            return Response({'error': 'Failed to update profile'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CashierListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(user_type='CASHIER')


class UserListView(generics.ListAPIView):
    queryset = User.objects.exclude(email='admin@gmail.com')
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        if self.request.user.user_type != 'ADMIN':
            raise PermissionDenied('Admin only')
        return super().get_queryset()

class RiderListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(user_type='RIDER', is_approved=True)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

class AllRidersListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(user_type='RIDER')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

class CustomerListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(user_type='CUSTOMER').exclude(email='admin@gmail.com')

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    try:
        username = request.data.get('username')
        password = request.data.get('password')
        
        if not username or not password:
            return Response({'error': 'Username and password required'}, status=status.HTTP_400_BAD_REQUEST)
        
        user = authenticate(username=username, password=password)
        
        if user is None:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        # Require email verification for customers, riders, and cashiers
        if user.user_type in ['CUSTOMER', 'RIDER', 'CASHIER'] and not user.is_email_verified:
            return Response({'error': 'Email not verified. Please verify your email before logging in.'}, status=status.HTTP_403_FORBIDDEN)
        
        # Check if user is approved
        if not user.is_approved:
            if getattr(user, 'is_rejected', False):
                reason = getattr(user, 'rejection_reason', '') or 'No reason provided'
                return Response({'error': f'Your account application was rejected.\n\nReason: {reason}\n\nPlease register again with the correct information.'}, status=status.HTTP_403_FORBIDDEN)
            user_type_label = {
                'RIDER': 'rider',
                'CUSTOMER': 'customer',
                'CASHIER': 'cashier',
            }.get(user.user_type, 'user')
            return Response({'error': f'Your {user_type_label} account is pending approval. Please wait for admin approval.'}, status=status.HTTP_403_FORBIDDEN)
        
        # Set rider online status if user is a rider
        if user.user_type == 'RIDER':
            try:
                user.is_online = True
                user.save(update_fields=['is_online'])
            except Exception as e:
                # Log error but don't fail login
                print(f"Failed to set online status: {e}")
        
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user_type': user.user_type,
            'user_id': user.id,
            'username': user.username,
        })
    except Exception as e:
        # Catch any unexpected errors
        print(f"Login error: {e}")
        return Response({'error': 'An error occurred during login. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_location(request):
    user = request.user
    if user.user_type != 'RIDER':
        return Response({'error': 'Only riders can update location'}, status=status.HTTP_403_FORBIDDEN)
    
    latitude = request.data.get('latitude')
    longitude = request.data.get('longitude')
    
    if latitude is None or longitude is None:
        return Response({'error': 'Latitude and longitude required'}, status=status.HTTP_400_BAD_REQUEST)
    
    user.current_latitude = latitude
    user.current_longitude = longitude
    user.location_updated_at = timezone.now()
    user.save()
    
    return Response({'message': 'Location updated successfully'})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_user(request, user_id):
    if request.user.user_type != 'ADMIN':
        return Response({'error': 'Only admins can approve users'}, status=status.HTTP_403_FORBIDDEN)
    try:
        user = User.objects.get(id=user_id)
        user.is_approved = True
        user.is_rejected = False
        user.rejection_reason = None
        user.save(update_fields=['is_approved', 'is_rejected', 'rejection_reason'])
        try:
            send_system_email(
                'Your JRNZ Tracking Express account has been approved',
                f'Hi {user.first_name},\n\nGreat news! Your account has been approved. You can now log in to JRNZ Tracking Express.\n\nWelcome aboard!\n\nJRNZ Tracking Express Team',
                [user.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f'Approval email error: {e}')
        return Response({'message': f'{user.user_type.title()} {user.username} approved successfully'})
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


# Backward-compatible alias for existing clients still using the old route/function name.
approve_rider = approve_user

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def assign_branch(request, user_id):
    if request.user.user_type != 'ADMIN':
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
    branch_id = request.data.get('branch_id')
    try:
        rider = User.objects.get(id=user_id, user_type__in=['RIDER', 'CASHIER'])
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    if branch_id is None:
        rider.branch = None
    else:
        try:
            branch = Branch.objects.get(id=branch_id, is_active=True)
        except Branch.DoesNotExist:
            return Response({'error': 'Branch not found'}, status=status.HTTP_404_NOT_FOUND)
        rider.branch = branch
    rider.save(update_fields=['branch'])
    return Response({'message': 'Branch assigned successfully', 'branch_id': branch_id})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reject_user(request, user_id):
    if request.user.user_type != 'ADMIN':
        return Response({'error': 'Only admins can reject users'}, status=status.HTTP_403_FORBIDDEN)
    reason = (request.data.get('reason') or '').strip()
    if not reason:
        return Response({'error': 'Rejection reason is required'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        user = User.objects.get(id=user_id)
        user.is_approved = False
        user.is_rejected = True
        user.rejection_reason = reason
        user.save(update_fields=['is_approved', 'is_rejected', 'rejection_reason'])
        try:
            send_system_email(
                'Your JRNZ Tracking Express account application was not approved',
                f'Hi {user.first_name},\n\nWe have reviewed your account application and unfortunately we are unable to approve it at this time.\n\nReason: {reason}\n\nIf you believe this is a mistake or would like to reapply, please register again with the correct information.\n\nJRNZ Tracking Express Team',
                [user.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f'Rejection email error: {e}')
        user.delete()
        return Response({'message': f'User rejected and removed successfully'})
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_push_token(request, user_id):
    if request.user.id != user_id:
        return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
    
    push_token = request.data.get('push_token')
    if not push_token:
        return Response({'error': 'Push token required'}, status=status.HTTP_400_BAD_REQUEST)
    
    user = request.user
    user.push_token = push_token
    user.save()
    
    return Response({'message': 'Push token saved successfully'})

@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email(request):
    email = (request.data.get('email') or '').strip().lower()
    code = (request.data.get('code') or '').strip()

    if not email or not code:
        return Response({'error': 'Email and verification code are required'}, status=status.HTTP_400_BAD_REQUEST)

    # --- Pending registration path (user not yet created) ---
    try:
        pending = PendingRegistration.objects.get(email__iexact=email)

        if pending.is_expired():
            pending.delete()
            return Response({'error': 'Verification code expired. Please register again.'}, status=status.HTTP_400_BAD_REQUEST)

        if code != pending.code:
            return Response({'error': 'Invalid verification code'}, status=status.HTTP_400_BAD_REQUEST)

        payload = json.loads(pending.data)

        # Race condition guard
        if User.objects.filter(username__iexact=payload['username']).exists():
            pending.delete()
            return Response({'error': 'This username was just taken. Please register again with a different username.'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email__iexact=email).exists():
            pending.delete()
            return Response({'error': 'An account with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        user_type = payload.get('user_type', 'CUSTOMER')
        user = User.objects.create_user(
            username=payload['username'],
            email=email,
            password=payload['password'],
            first_name=payload['first_name'],
            last_name=payload['last_name'],
            user_type=user_type,
            phone=payload['phone'],
            address=payload['address'],
            date_of_birth=payload.get('date_of_birth') or None,
            vehicle_brand=payload.get('vehicle_brand', ''),
            vehicle_plate=payload.get('vehicle_plate', ''),
            vehicle_color=payload.get('vehicle_color', ''),
            license_number=payload.get('license_number', ''),
            branch_id=payload.get('branch_id'),
        )
        user.is_email_verified = True

        # Save identity image and verification photos for riders
        if user_type == 'RIDER':
            import base64
            from django.core.files.base import ContentFile
            if pending.image_data and pending.image_name:
                image_bytes = base64.b64decode(pending.image_data)
                user.identity_image.save(pending.image_name, ContentFile(image_bytes), save=False)
            extra_images = json.loads(getattr(pending, 'extra_data', '{}') or '{}')
            for photo_field in ['photo_front', 'photo_left', 'photo_right', 'motorcycle_registration']:
                if photo_field in extra_images:
                    img_bytes = base64.b64decode(extra_images[photo_field]['data'])
                    getattr(user, photo_field).save(extra_images[photo_field]['name'], ContentFile(img_bytes), save=False)

        user.save()

        pending.delete()
        success_msg = 'Email verified successfully. Your application is pending admin approval.' if user_type in ['RIDER', 'CASHIER'] else 'Email verified successfully. You can now sign in.'
        return Response({'message': success_msg}, status=status.HTTP_201_CREATED)

    except PendingRegistration.DoesNotExist:
        pass

    # --- Legacy path: user already exists but unverified ---
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({'error': 'No pending registration found for this email. Please register again.'}, status=status.HTTP_404_NOT_FOUND)

    if user.is_email_verified:
        return Response({'message': 'Email already verified'}, status=status.HTTP_200_OK)

    if not user.email_verification_code or not user.email_verification_expires:
        return Response({'error': 'No active verification code. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)

    if user.email_verification_expires < timezone.now():
        return Response({'error': 'Verification code expired. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)

    if code != user.email_verification_code:
        return Response({'error': 'Invalid verification code'}, status=status.HTTP_400_BAD_REQUEST)

    user.is_email_verified = True
    user.email_verification_code = None
    user.email_verification_expires = None
    user.save(update_fields=['is_email_verified', 'email_verification_code', 'email_verification_expires'])

    return Response({'message': 'Email verified successfully'})

@api_view(['POST'])
@permission_classes([AllowAny])
def resend_verification(request):
    email = (request.data.get('email') or '').strip().lower()

    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

    # --- Pending registration path ---
    try:
        pending = PendingRegistration.objects.get(email__iexact=email)
        code = _generate_verification_code()
        pending.code = code
        pending.expires_at = timezone.now() + timedelta(minutes=10)
        pending.save(update_fields=['code', 'expires_at'])
        try:
            _send_otp_email(email, code)
        except Exception as e:
            print(f"Resend verification error: {e}")
            return _mail_error_response('Failed to send verification code. Please try again later.', e)
        return Response({'message': 'Verification code sent'})
    except PendingRegistration.DoesNotExist:
        pass

    # --- Legacy path ---
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({'error': 'No pending registration found for this email. Please register again.'}, status=status.HTTP_404_NOT_FOUND)

    if user.is_email_verified:
        return Response({'message': 'Email already verified'}, status=status.HTTP_200_OK)

    try:
        _send_verification_email(user)
    except Exception as e:
        print(f"Resend verification error: {e}")
        return _mail_error_response('Failed to send verification code. Please try again later.', e)

    return Response({'message': 'Verification code sent'})


@api_view(['POST'])
@permission_classes([AllowAny])
def reset_mpin(request):
    email = (request.data.get('email') or '').strip().lower()
    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        user = User.objects.get(email__iexact=email, user_type__in=['RIDER', 'CASHIER'])
    except User.DoesNotExist:
        return Response({'error': 'No rider or cashier account found with that email.'}, status=status.HTTP_404_NOT_FOUND)

    new_mpin = f"{random.randint(0, 999999):06d}"
    try:
        send_system_email(
            subject='Your JRNZ Tracking Express MPIN Reset',
            message=(
                f'Hi {user.first_name},\n\n'
                f'Your new MPIN is: {new_mpin}\n\n'
                f'Please log in and change your MPIN immediately after using this code.\n\n'
                f'JRNZ Tracking Express Team'
            ),
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as e:
        print(f'MPIN reset email error: {e}')
        return _mail_error_response('Failed to send email. Please try again.', e)

    return Response({'mpin': new_mpin, 'user_id': user.id}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password_request(request):
    email = (request.data.get('email') or '').strip().lower()
    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({'error': 'No account found with that email.'}, status=status.HTTP_404_NOT_FOUND)
    code = _generate_verification_code()
    user.email_verification_code = code
    user.email_verification_expires = timezone.now() + timedelta(minutes=10)
    user.save(update_fields=['email_verification_code', 'email_verification_expires'])
    try:
        send_system_email(
            subject='Your JRNZ Tracking Express password reset code',
            message=(
                f'Hi {user.first_name},\n\n'
                f'Your password reset code is: {code}\n\n'
                f'This code expires in 10 minutes. If you did not request this, ignore this email.\n\n'
                f'JRNZ Tracking Express Team'
            ),
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as e:
        print(f'Forgot password email error: {e}')
        return _mail_error_response('Failed to send reset code. Please try again.', e)
    return Response({'message': 'Password reset code sent to your email.'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password_verify(request):
    email = (request.data.get('email') or '').strip().lower()
    code = (request.data.get('code') or '').strip()
    if not email or not code:
        return Response({'error': 'Email and code are required'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({'error': 'No account found with that email.'}, status=status.HTTP_404_NOT_FOUND)
    if not user.email_verification_code or not user.email_verification_expires:
        return Response({'error': 'No active reset code. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)
    if user.email_verification_expires < timezone.now():
        return Response({'error': 'Reset code expired. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)
    if code != user.email_verification_code:
        return Response({'error': 'Invalid reset code.'}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'message': 'Code verified.'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password_reset(request):
    email = (request.data.get('email') or '').strip().lower()
    code = (request.data.get('code') or '').strip()
    new_password = (request.data.get('new_password') or '').strip()
    if not email or not code or not new_password:
        return Response({'error': 'Email, code, and new_password are required'}, status=status.HTTP_400_BAD_REQUEST)
    if len(new_password) < 8:
        return Response({'error': 'Password must be at least 8 characters.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({'error': 'No account found with that email.'}, status=status.HTTP_404_NOT_FOUND)
    if not user.email_verification_code or not user.email_verification_expires:
        return Response({'error': 'No active reset code. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)
    if user.email_verification_expires < timezone.now():
        return Response({'error': 'Reset code expired. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)
    if code != user.email_verification_code:
        return Response({'error': 'Invalid reset code.'}, status=status.HTTP_400_BAD_REQUEST)
    user.set_password(new_password)
    user.email_verification_code = None
    user.email_verification_expires = None
    user.save(update_fields=['password', 'email_verification_code', 'email_verification_expires'])
    return Response({'message': 'Password reset successfully.'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def create_support_ticket(request):
    serializer = SupportTicketCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    concern = serializer.validated_data.get('concern', '').lower()
    concern_type = serializer.validated_data.get('concern_type')
    if concern_type == 'GENERAL':
        if 'rider' in concern:
            concern_type = 'RIDER_APPLICATION'
        elif 'cashier' in concern:
            concern_type = 'CASHIER_APPLICATION'

    ticket = serializer.save(
        concern_type=concern_type,
        submitted_by=request.user if getattr(request.user, 'is_authenticated', False) else None,
    )

    support_ticket_email = getattr(settings, 'SUPPORT_TICKET_EMAIL', 'deliverytrack2026@gmail.com')
    if support_ticket_email:
        try:
            send_system_email(
                subject=f'New Support Concern: {ticket.get_concern_type_display()}',
                message=(
                    f'New concern received from landing chatbot.\n\n'
                    f'Name: {ticket.name}\n'
                    f'Email: {ticket.email}\n'
                    f'Type: {ticket.get_concern_type_display()}\n\n'
                    f'Concern:\n{ticket.concern}\n\n'
                    f'Ticket ID: {ticket.id}'
                ),
                recipient_list=[support_ticket_email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"Support ticket email error: {e}")

    return Response(
        {
            'message': 'Your concern was sent successfully. Staff will review it shortly.',
            'ticket': SupportTicketSerializer(ticket).data,
        },
        status=status.HTTP_201_CREATED
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_support_tickets(request):
    if not _is_staff_ticket_manager(request.user):
        return Response({'error': 'Only admin or cashier can manage support concerns.'}, status=status.HTTP_403_FORBIDDEN)

    queryset = SupportTicket.objects.all()
    status_filter = (request.query_params.get('status') or '').upper()
    if status_filter in ['PENDING', 'IN_REVIEW', 'RESOLVED']:
        queryset = queryset.filter(status=status_filter)

    concern_type = (request.query_params.get('concern_type') or '').upper()
    if concern_type in ['GENERAL', 'RIDER_APPLICATION', 'CASHIER_APPLICATION']:
        queryset = queryset.filter(concern_type=concern_type)

    serializer = SupportTicketSerializer(queryset, many=True)
    return Response(serializer.data)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_support_ticket(request, ticket_id):
    if not _is_staff_ticket_manager(request.user):
        return Response({'error': 'Only admin or cashier can manage support concerns.'}, status=status.HTTP_403_FORBIDDEN)

    try:
        ticket = SupportTicket.objects.get(id=ticket_id)
    except SupportTicket.DoesNotExist:
        return Response({'error': 'Support ticket not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = SupportTicketUpdateSerializer(ticket, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    updated_ticket = serializer.save(handled_by=request.user)
    if updated_ticket.status == 'RESOLVED' and updated_ticket.resolved_at is None:
        updated_ticket.resolved_at = timezone.now()
        updated_ticket.save(update_fields=['resolved_at'])
    elif updated_ticket.status != 'RESOLVED' and updated_ticket.resolved_at is not None:
        updated_ticket.resolved_at = None
        updated_ticket.save(update_fields=['resolved_at'])

    return Response({
        'message': 'Support ticket updated.',
        'ticket': SupportTicketSerializer(updated_ticket).data,
    })
