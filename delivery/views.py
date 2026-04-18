from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Avg, Count, Q
from .models import Delivery, Notification, Rating, ChatMessage, DeliveryFeeConfig, DeliveryRequest
from .serializers import DeliverySerializer, NotificationSerializer, RatingSerializer, DeliveryRequestSerializer
from .notifications import notify_rider_new_delivery, notify_customer_status_update, notify_rider_payment_received
from user.models import User, Branch
from math import radians, sin, cos, sqrt, atan2
import random
import string

STATUS_CHOICES_MAP = dict(Delivery.STATUS_CHOICES)
ACTIVE_DELIVERY_STATUSES = ['PENDING', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY']
ALLOWED_STATUS_TRANSITIONS = {
    'PENDING': {'PICKED_UP'},
    'PICKED_UP': {'IN_TRANSIT', 'FAILED'},
    'IN_TRANSIT': {'OUT_FOR_DELIVERY', 'FAILED'},
    'OUT_FOR_DELIVERY': {'DELIVERED', 'FAILED'},
    'FAILED': {'OUT_FOR_DELIVERY'},
    'DELIVERED': set(),
    'CANCELLED': set(),
}


def _mask_address(address):
    if not address:
        return None
    plain_address = address.split('|')[0].strip()
    if len(plain_address) <= 12:
        return plain_address
    return f"{plain_address[:8]}...{plain_address[-4:]}"


def _mask_rider_name(rider):
    if not rider:
        return None
    full_name = (rider.get_full_name() or '').strip()
    if not full_name:
        return None
    parts = full_name.split()
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {' '.join(f'{p[0]}.' for p in parts[1:])}"


def _to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_coordinates_from_address(address):
    """
    Accepts address formats like:
    - "123 Main St|14.5995,120.9842"
    - "14.5995,120.9842"
    Returns (lat, lng) or (None, None).
    """
    if not address:
        return None, None

    candidate = address.split('|')[-1].strip()
    parts = [part.strip() for part in candidate.split(',')]
    if len(parts) != 2:
        return None, None

    lat = _to_float(parts[0])
    lng = _to_float(parts[1])
    if lat is None or lng is None:
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None, None
    return lat, lng


def _rider_coordinates(rider):
    """
    Prefer rider live location. Fallback to assigned branch coordinates.
    """
    live_lat = _to_float(rider.current_latitude)
    live_lng = _to_float(rider.current_longitude)
    if live_lat is not None and live_lng is not None:
        return live_lat, live_lng

    if rider.branch:
        branch_lat = _to_float(rider.branch.latitude)
        branch_lng = _to_float(rider.branch.longitude)
        if branch_lat is not None and branch_lng is not None:
            return branch_lat, branch_lng

    return None, None


def _distance_km(lat1, lng1, lat2, lng2):
    """Haversine distance in kilometers."""
    r = 6371.0
    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lng / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


def _nearest_active_branch(lat, lng):
    """
    Returns (branch, distance_km) for the nearest active branch with map coordinates.
    """
    nearest_branch = None
    nearest_distance = None
    branches = Branch.objects.filter(is_active=True).exclude(latitude__isnull=True).exclude(longitude__isnull=True)
    for branch in branches:
        branch_lat = _to_float(branch.latitude)
        branch_lng = _to_float(branch.longitude)
        if branch_lat is None or branch_lng is None:
            continue
        distance = _distance_km(branch_lat, branch_lng, lat, lng)
        if nearest_distance is None or distance < nearest_distance:
            nearest_distance = distance
            nearest_branch = branch
    return nearest_branch, nearest_distance


@api_view(['GET'])
@permission_classes([AllowAny])
def get_fee_config(request):
    config = DeliveryFeeConfig.get_config()
    return Response({
        'base_fee': str(config.base_fee),
        'per_kg_rate': str(config.per_kg_rate),
        'per_item_rate': str(config.per_item_rate),
    })

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_fee_config(request):
    if request.user.user_type != 'ADMIN':
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
    config = DeliveryFeeConfig.get_config()
    try:
        if 'base_fee' in request.data:
            config.base_fee = float(request.data['base_fee'])
        if 'per_kg_rate' in request.data:
            config.per_kg_rate = float(request.data['per_kg_rate'])
        if 'per_item_rate' in request.data:
            config.per_item_rate = float(request.data['per_item_rate'])
        config.save()
    except (ValueError, TypeError):
        return Response({'error': 'Invalid values'}, status=status.HTTP_400_BAD_REQUEST)
    return Response({
        'base_fee': str(config.base_fee),
        'per_kg_rate': str(config.per_kg_rate),
        'per_item_rate': str(config.per_item_rate),
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def track_by_number(request, tracking_number):
    normalized_tracking = tracking_number.strip()
    delivery = Delivery.objects.filter(tracking_number__iexact=normalized_tracking).first()
    if not delivery:
        return Response({'error': 'Tracking number not found'}, status=status.HTTP_404_NOT_FOUND)
    return Response({
        'tracking_number': delivery.tracking_number,
        'status': delivery.status,
        'estimated_time': delivery.estimated_time,
        'pickup_address': _mask_address(delivery.pickup_address),
        'delivery_address': _mask_address(delivery.delivery_address),
        'failure_reason': delivery.failure_reason,
        'created_at': delivery.created_at,
        'updated_at': delivery.updated_at,
        'rider_name': _mask_rider_name(delivery.rider),
    })

def auto_assign_rider(delivery):
    """
    Auto-assign the best available rider using:
    1) Delivery zone hub (nearest active hub to delivery address coordinates)
    2) Distance to delivery coordinates when available
    3) Active workload as tie-breaker
    """
    available_riders = User.objects.filter(
        user_type='RIDER',
        is_available=True,
        is_approved=True,
        is_online=True  # Only assign to online riders
    ).select_related('branch').annotate(
        active_jobs=Count(
            'rider_deliveries',
            filter=Q(rider_deliveries__status__in=ACTIVE_DELIVERY_STATUSES),
            distinct=True
        )
    )

    if not available_riders.exists():
        return None

    delivery_lat, delivery_lng = _extract_coordinates_from_address(delivery.delivery_address)
    if delivery_lat is not None and delivery_lng is not None:
        target_branch, _ = _nearest_active_branch(delivery_lat, delivery_lng)
        if not target_branch:
            return None
        candidate_riders = available_riders.filter(branch_id=target_branch.id)
        if not candidate_riders.exists():
            return None
    else:
        preferred_branch_id = getattr(delivery.customer, 'branch_id', None)
        if preferred_branch_id:
            candidate_riders = available_riders.filter(branch_id=preferred_branch_id)
            if not candidate_riders.exists():
                return None
        else:
            candidate_riders = available_riders

    if delivery_lat is None or delivery_lng is None:
        return sorted(candidate_riders, key=lambda rider: (rider.active_jobs, rider.id))[0]

    def sort_key(rider):
        rider_lat, rider_lng = _rider_coordinates(rider)
        if rider_lat is None or rider_lng is None:
            return (1, float('inf'), rider.active_jobs, rider.id)
        return (0, _distance_km(delivery_lat, delivery_lng, rider_lat, rider_lng), rider.active_jobs, rider.id)

    return sorted(candidate_riders, key=sort_key)[0]


MAX_RIDER_DISTANCE_KM = 30


def _validate_rider_assignment(rider, delivery):
    """
    Returns a Response error if the rider cannot be assigned, otherwise None.
    Checks:
    1. Rider must have a branch/hub assigned.
    2. Rider's branch must have map coordinates.
    3. Delivery address must include map coordinates.
    4. Rider must belong to the nearest active hub for the delivery address.
    5. The nearest hub must be within MAX_RIDER_DISTANCE_KM of the delivery address.
    """
    if not rider.branch:
        return Response(
            {'error': 'Rider has no Hub assigned. Please assign a Hub to this rider first.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    branch_lat = _to_float(rider.branch.latitude)
    branch_lng = _to_float(rider.branch.longitude)
    if branch_lat is None or branch_lng is None:
        return Response(
            {'error': f"Rider's Hub ({rider.branch.name}) has no map pin. Please update Hub coordinates first."},
            status=status.HTTP_400_BAD_REQUEST
        )

    delivery_lat, delivery_lng = _extract_coordinates_from_address(delivery.delivery_address)
    if delivery_lat is None or delivery_lng is None:
        return Response(
            {'error': 'Delivery address has no map pin. Please set the delivery location using the map first.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    nearest_branch, nearest_distance = _nearest_active_branch(delivery_lat, delivery_lng)
    if not nearest_branch:
        return Response(
            {'error': 'No active Hub with map pin is available. Please configure Hub coordinates first.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if rider.branch_id != nearest_branch.id:
        return Response(
            {
                'error': (
                    f"Delivery is outside rider's zone. Forward this parcel to {nearest_branch.name} "
                    f'and assign a rider from that Hub.'
                )
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if nearest_distance is not None and nearest_distance > MAX_RIDER_DISTANCE_KM:
        return Response(
            {
                'error': (
                    f'Nearest Hub ({nearest_branch.name}) is too far from delivery '
                    f'({nearest_distance:.1f}km away). Maximum allowed distance is {MAX_RIDER_DISTANCE_KM}km.'
                )
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    return None


def notify_cashiers(delivery, title, message):
    """Send notification to all active cashiers about a delivery update."""
    cashiers = User.objects.filter(user_type='CASHIER', is_active=True)
    for cashier in cashiers:
        Notification.objects.create(
            user=cashier,
            delivery=delivery,
            title=title,
            message=message,
        )

class DeliveryViewSet(viewsets.ModelViewSet):
    serializer_class = DeliverySerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'CUSTOMER':
            # Show deliveries they own OR cashier-created ones where sender phone matches
            from django.db.models import Q
            return Delivery.objects.filter(
                Q(customer=user) | Q(sender_contact=user.phone)
            ).distinct()
        elif user.user_type == 'RIDER':
            return Delivery.objects.filter(rider=user)
        else:  # ADMIN or CASHIER
            return Delivery.objects.all()
    
    def perform_create(self, serializer):
        tracking_number = 'TRK-' + ''.join(random.choices(string.digits, k=10))
        if self.request.user.user_type == 'CASHIER':
            # Try to link to existing customer account by sender phone number
            sender_contact = self.request.data.get('sender_contact', '')
            linked_customer = None
            if sender_contact:
                try:
                    linked_customer = User.objects.get(phone=sender_contact, user_type='CUSTOMER')
                except User.DoesNotExist:
                    pass
            serializer.save(
                customer=linked_customer or self.request.user,
                tracking_number=tracking_number,
                is_approved=True,
                pickup_address='Branch Drop-off',
            )
        else:
            serializer.save(customer=self.request.user, tracking_number=tracking_number)
    def _check_rider_assignment(self, request, *args, **kwargs):
        rider_id = request.data.get('rider')
        if not rider_id:
            return None
        try:
            rider = User.objects.select_related('branch').get(id=rider_id, user_type='RIDER')
        except User.DoesNotExist:
            return Response({'error': 'Rider not found'}, status=status.HTTP_404_NOT_FOUND)

        if not rider.is_approved:
            return Response(
                {'error': 'Cannot assign delivery to unapproved rider.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not rider.is_online:
            return Response(
                {'error': 'Cannot assign delivery to offline rider. Please select an online rider.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        delivery = self.get_object()
        return _validate_rider_assignment(rider, delivery)

    def update(self, request, *args, **kwargs):
        if 'rider' in request.data:
            error = self._check_rider_assignment(request, *args, **kwargs)
            if error:
                return error
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if 'rider' in request.data:
            error = self._check_rider_assignment(request, *args, **kwargs)
            if error:
                return error
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a delivery (customer or admin)."""
        delivery = self.get_object()

        if request.user.user_type not in ('CUSTOMER', 'ADMIN'):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.user_type == 'CUSTOMER' and delivery.customer != request.user:
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        if delivery.status != 'PENDING':
            return Response({'error': 'Only pending deliveries can be cancelled'}, status=status.HTTP_400_BAD_REQUEST)

        delivery.status = 'CANCELLED'
        delivery.progress = 0
        delivery.estimated_time = None
        delivery.save()

        Notification.objects.create(
            user=delivery.customer,
            delivery=delivery,
            title='Delivery Cancelled',
            message=f'Delivery {delivery.tracking_number} has been cancelled.'
        )
        if delivery.rider:
            Notification.objects.create(
                user=delivery.rider,
                delivery=delivery,
                title='Delivery Cancelled',
                message=f'Delivery {delivery.tracking_number} has been cancelled by the customer.'
            )

        return Response(DeliverySerializer(delivery).data)
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        delivery = self.get_object()
        new_status_raw = request.data.get('status')
        new_status = (new_status_raw or '').strip().upper()
        
        if delivery.rider != request.user and request.user.user_type != 'ADMIN':
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        if not new_status:
            return Response({'error': 'Status is required'}, status=status.HTTP_400_BAD_REQUEST)

        if new_status not in STATUS_CHOICES_MAP:
            return Response({'error': 'Invalid status value'}, status=status.HTTP_400_BAD_REQUEST)

        if new_status != delivery.status and request.user.user_type != 'ADMIN':
            allowed_next = ALLOWED_STATUS_TRANSITIONS.get(delivery.status, set())
            if new_status not in allowed_next:
                return Response(
                    {'error': f'Invalid transition from {delivery.status} to {new_status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if delivery.status in ('DELIVERED', 'CANCELLED') and new_status != delivery.status:
            return Response(
                {'error': f'{delivery.status.title()} deliveries cannot be updated'},
                status=status.HTTP_400_BAD_REQUEST
            )

        failure_reason = request.data.get('failure_reason')
        if new_status == 'FAILED' and not (failure_reason or delivery.failure_reason):
            return Response(
                {'error': 'failure_reason is required when status is FAILED'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = delivery.status
        delivery.status = new_status
        
        # Handle proof of delivery image
        if 'proof_of_delivery' in request.FILES:
            delivery.proof_of_delivery = request.FILES['proof_of_delivery']
        
        # Handle delivery notes
        if 'notes' in request.data:
            delivery.notes = request.data.get('notes')
        
        # Handle failure reason
        if new_status == 'FAILED' and 'failure_reason' in request.data:
            delivery.failure_reason = failure_reason
            if old_status != 'FAILED':
                delivery.delivery_attempts += 1
            
            # Check if max attempts reached
            if delivery.delivery_attempts >= delivery.max_attempts:
                # Final failure - return to sender
                Notification.objects.create(
                    user=delivery.customer,
                    delivery=delivery,
                    title='Delivery Failed - Max Attempts Reached',
                    message=f'Package {delivery.tracking_number} could not be delivered after {delivery.max_attempts} attempts. Package will be returned to sender.'
                )
            else:
                # Still have attempts left - can reschedule
                remaining = delivery.max_attempts - delivery.delivery_attempts
                Notification.objects.create(
                    user=delivery.customer,
                    delivery=delivery,
                    title=f'Delivery Attempt {delivery.delivery_attempts} Failed',
                    message=f'Package {delivery.tracking_number} delivery failed. Reason: {delivery.failure_reason}. {remaining} attempt(s) remaining. We will try again tomorrow.'
                )
        
        # Update progress based on status
        status_progress = {
            'PENDING': 0,
            'PICKED_UP': 25,
            'IN_TRANSIT': 50,
            'OUT_FOR_DELIVERY': 75,
            'DELIVERED': 100,
        }
        delivery.progress = status_progress.get(new_status, delivery.progress)

        # Set ETA based on status
        eta_map = {
            'PICKED_UP': '45-60 mins',
            'IN_TRANSIT': '30-45 mins',
            'OUT_FOR_DELIVERY': '10-20 mins',
            'DELIVERED': None,
            'FAILED': None,
            'CANCELLED': None,
        }
        if new_status in eta_map:
            delivery.estimated_time = eta_map[new_status]

        delivery.save()
        
        # Credit rider wallet when delivered
        if new_status == 'DELIVERED' and old_status != 'DELIVERED' and delivery.rider:
            from payment.models import RiderWallet, WalletTransaction
            wallet, created = RiderWallet.objects.get_or_create(rider=delivery.rider)
            
            balance_before = wallet.balance
            wallet.balance += delivery.delivery_fee
            wallet.total_earned += delivery.delivery_fee
            wallet.save()
            
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='EARNING',
                amount=delivery.delivery_fee,
                balance_before=balance_before,
                balance_after=wallet.balance,
                delivery=delivery,
                description=f'Delivery fee for {delivery.tracking_number}'
            )
        
        # Create notification for customer
        if old_status != new_status:
            Notification.objects.create(
                user=delivery.customer,
                delivery=delivery,
                title=f'Delivery Status Updated',
                message=f'Your package {delivery.tracking_number} is now {new_status.replace("_", " ").title()}'
            )
            # Send push notification
            notify_customer_status_update(delivery.customer, delivery, new_status)

            # Notify cashiers about delivery status changes
            cashier_messages = {
                'PICKED_UP': f'🚚 Rider {delivery.rider.get_full_name() if delivery.rider else "Unknown"} picked up {delivery.tracking_number} from branch.',
                'IN_TRANSIT': f'🚚 {delivery.tracking_number} is now in transit to {delivery.delivery_address.split("|")[0][:40]}.',
                'DELIVERED': f'✅ {delivery.tracking_number} has been delivered successfully.',
                'FAILED': f'❌ {delivery.tracking_number} delivery failed. Reason: {delivery.failure_reason or "Not specified"}.',
                'OUT_FOR_DELIVERY': f'📦 {delivery.tracking_number} is out for delivery.',
            }
            if new_status in cashier_messages:
                notify_cashiers(
                    delivery,
                    title=f'Parcel Update — {new_status.replace("_", " ").title()}',
                    message=cashier_messages[new_status],
                )
        
        return Response(DeliverySerializer(delivery).data)
    
    @action(detail=True, methods=['get', 'post'])
    def chat(self, request, pk=None):
        delivery = self.get_object()
        user = request.user

        # Only customer or assigned rider can chat
        if user != delivery.customer and user != delivery.rider and user.user_type != 'ADMIN':
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'POST':
            message = request.data.get('message', '').strip()
            if not message:
                return Response({'error': 'Message cannot be empty'}, status=status.HTTP_400_BAD_REQUEST)
            msg = ChatMessage.objects.create(delivery=delivery, sender=user, message=message)
            return Response({
                'id': msg.id,
                'sender_id': user.id,
                'sender_name': user.get_full_name() or user.username,
                'sender_type': user.user_type,
                'message': msg.message,
                'created_at': msg.created_at,
            }, status=status.HTTP_201_CREATED)

        messages = delivery.messages.select_related('sender').all()
        return Response([{
            'id': m.id,
            'sender_id': m.sender.id,
            'sender_name': m.sender.get_full_name() or m.sender.username,
            'sender_type': m.sender.user_type,
            'message': m.message,
            'created_at': m.created_at,
        } for m in messages])

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Only admins can approve'}, status=status.HTTP_403_FORBIDDEN)
        
        delivery = self.get_object()
        delivery.is_approved = True
        
        # Auto-assign rider
        rider = auto_assign_rider(delivery)
        if rider:
            validation_error = _validate_rider_assignment(rider, delivery)
            if validation_error:
                rider = None
        if rider:
            delivery.rider = rider
            delivery.status = 'PENDING'  # Ready for pickup
            
            # Notify rider
            Notification.objects.create(
                user=rider,
                delivery=delivery,
                title='New Delivery Assigned',
                message=f'You have been assigned delivery {delivery.tracking_number}. Please pick up from {delivery.pickup_address}'
            )
            # Send push notification
            notify_rider_new_delivery(rider, delivery)
        
        delivery.save()
        
        # Notify customer
        Notification.objects.create(
            user=delivery.customer,
            delivery=delivery,
            title='Delivery Approved',
            message=f'Your delivery {delivery.tracking_number} has been approved' + 
                   (f' and assigned to rider {rider.get_full_name()}' if rider else ' and is awaiting rider assignment')
        )
        
        return Response({
            'message': 'Delivery approved',
            'rider_assigned': rider.get_full_name() if rider else None
        })
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        user = request.user
        if user.user_type == 'CUSTOMER':
            from django.db.models import Q
            deliveries = Delivery.objects.filter(
                Q(customer=user) | Q(sender_contact=user.phone),
                is_approved=True,
                status__in=['PENDING', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY']
            ).distinct()
        elif user.user_type == 'RIDER':
            deliveries = Delivery.objects.filter(
                rider=user,
                status__in=['PENDING', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY']
            )
        else:
            deliveries = Delivery.objects.filter(
                status__in=['PENDING', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY']
            )
        
        serializer = self.get_serializer(deliveries, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def rider_stats(self, request):
        from django.db.models import Sum, Avg, Count
        from datetime import datetime, timedelta
        from django.utils import timezone
        
        rider = request.user
        now = timezone.now()
        today_start = timezone.make_aware(datetime.combine(now.date(), datetime.min.time()))
        today_end = timezone.make_aware(datetime.combine(now.date(), datetime.max.time()))
        week_start = timezone.make_aware(datetime.combine(now.date() - timedelta(days=now.weekday()), datetime.min.time()))
        month_start = timezone.make_aware(datetime.combine(now.date().replace(day=1), datetime.min.time()))
        
        # If not a rider, return zeros
        if rider.user_type != 'RIDER':
            return Response({
                'today_earnings': 0,
                'today_count': 0,
                'week_earnings': 0,
                'week_count': 0,
                'month_earnings': 0,
                'total_earnings': 0,
                'wallet_balance': 0,
                'total_completed': 0,
                'active_count': 0,
                'average_rating': 0,
                'on_time_rate': 0
            })
        
        # Try to get wallet and transactions, fallback to delivery-based calculation
        try:
            from payment.models import RiderWallet, WalletTransaction
            wallet, created = RiderWallet.objects.get_or_create(rider=rider)
            
            # Today's earnings from wallet transactions
            today_earnings = WalletTransaction.objects.filter(
                wallet=wallet,
                transaction_type='EARNING',
                created_at__gte=today_start,
                created_at__lte=today_end
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            # Week earnings
            week_earnings = WalletTransaction.objects.filter(
                wallet=wallet,
                transaction_type='EARNING',
                created_at__gte=week_start
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            # Month earnings
            month_earnings = WalletTransaction.objects.filter(
                wallet=wallet,
                transaction_type='EARNING',
                created_at__gte=month_start
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            # Total earnings and balance from wallet
            total_earnings = wallet.total_earned
            wallet_balance = wallet.balance
        except Exception as e:
            # Fallback to delivery-based calculation if payment app not ready
            print(f"Wallet query error: {e}")
            today_earnings = Delivery.objects.filter(
                rider=rider,
                status='DELIVERED',
                updated_at__gte=today_start,
                updated_at__lte=today_end
            ).aggregate(total=Sum('delivery_fee'))['total'] or 0
            
            week_earnings = Delivery.objects.filter(
                rider=rider,
                status='DELIVERED',
                updated_at__gte=week_start
            ).aggregate(total=Sum('delivery_fee'))['total'] or 0
            
            month_earnings = Delivery.objects.filter(
                rider=rider,
                status='DELIVERED',
                updated_at__gte=month_start
            ).aggregate(total=Sum('delivery_fee'))['total'] or 0
            
            total_earnings = Delivery.objects.filter(
                rider=rider,
                status='DELIVERED'
            ).aggregate(total=Sum('delivery_fee'))['total'] or 0
            
            wallet_balance = 0
        
        today_count = Delivery.objects.filter(
            rider=rider,
            status='DELIVERED',
            updated_at__gte=today_start,
            updated_at__lte=today_end
        ).count()
        
        week_count = Delivery.objects.filter(
            rider=rider,
            status='DELIVERED',
            updated_at__gte=week_start
        ).count()
        
        # Total stats
        total_completed = Delivery.objects.filter(rider=rider, status='DELIVERED').count()
        active_count = Delivery.objects.filter(
            rider=rider,
            status__in=['PENDING', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY']
        ).count()
        
        # Average rating
        avg_rating = Rating.objects.filter(rider=rider).aggregate(avg=Avg('rating'))['avg'] or 0
        
        return Response({
            'today_earnings': float(today_earnings),
            'today_count': today_count,
            'week_earnings': float(week_earnings),
            'week_count': week_count,
            'month_earnings': float(month_earnings),
            'total_earnings': float(total_earnings),
            'wallet_balance': float(wallet_balance),
            'total_completed': total_completed,
            'active_count': active_count,
            'average_rating': round(float(avg_rating), 1) if avg_rating else 0,
            'on_time_rate': 95  # Placeholder - implement actual calculation
        })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_delivery_request(request):
    if request.user.user_type != 'CUSTOMER':
        return Response({'error': 'Customers only'}, status=status.HTTP_403_FORBIDDEN)
    serializer = DeliveryRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer.save(customer=request.user)
    # Notify all cashiers
    for cashier in User.objects.filter(user_type='CASHIER', is_active=True):
        Notification.objects.create(
            user=cashier,
            title='📦 New Delivery Request',
            message=f'{request.user.get_full_name() or request.user.username} sent a delivery request to the cashier.',
        )
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_delivery_requests(request):
    if request.user.user_type not in ('CASHIER', 'ADMIN'):
        return Response({'error': 'Cashier/Admin only'}, status=status.HTTP_403_FORBIDDEN)
    requests_qs = DeliveryRequest.objects.filter(status='PENDING')
    return Response(DeliveryRequestSerializer(requests_qs, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def accept_delivery_request(request, request_id):
    if request.user.user_type not in ('CASHIER', 'ADMIN'):
        return Response({'error': 'Cashier/Admin only'}, status=status.HTTP_403_FORBIDDEN)
    try:
        dr = DeliveryRequest.objects.get(id=request_id, status='PENDING')
    except DeliveryRequest.DoesNotExist:
        return Response({'error': 'Request not found'}, status=status.HTTP_404_NOT_FOUND)
    dr.status = 'ACCEPTED'
    dr.save(update_fields=['status'])
    return Response(DeliveryRequestSerializer(dr).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_delivery_request(request, request_id):
    if request.user.user_type not in ('CUSTOMER', 'CASHIER', 'ADMIN'):
        return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
    try:
        dr = DeliveryRequest.objects.get(id=request_id, status='PENDING')
    except DeliveryRequest.DoesNotExist:
        return Response({'error': 'Request not found'}, status=status.HTTP_404_NOT_FOUND)
    dr.status = 'CANCELLED'
    dr.save(update_fields=['status'])
    return Response({'message': 'Request cancelled'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_gcash_proof(request, delivery_id):
    if request.user.user_type != 'RIDER':
        return Response({'error': 'Riders only'}, status=status.HTTP_403_FORBIDDEN)
    try:
        delivery = Delivery.objects.get(id=delivery_id, rider=request.user)
    except Delivery.DoesNotExist:
        return Response({'error': 'Delivery not found'}, status=status.HTTP_404_NOT_FOUND)
    if 'gcash_proof' not in request.FILES:
        return Response({'error': 'No image provided'}, status=status.HTTP_400_BAD_REQUEST)
    delivery.gcash_proof = request.FILES['gcash_proof']
    delivery.save(update_fields=['gcash_proof'])
    return Response({'message': 'GCash proof uploaded', 'gcash_proof': delivery.gcash_proof.url})


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'message': 'All notifications marked as read'})
    
    @action(detail=False, methods=['post'])
    def clear_all(self, request):
        Notification.objects.filter(user=request.user).delete()
        return Response({'message': 'All notifications cleared'})
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'count': count})

class RatingViewSet(viewsets.ModelViewSet):
    serializer_class = RatingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'CUSTOMER':
            return Rating.objects.filter(customer=user)
        elif user.user_type == 'RIDER':
            return Rating.objects.filter(rider=user)
        return Rating.objects.all()
    
    def perform_create(self, serializer):
        delivery = serializer.validated_data['delivery']
        if delivery.customer != self.request.user:
            from rest_framework.exceptions import ValidationError
            raise ValidationError('You can only rate your own deliveries')
        if delivery.status != 'DELIVERED':
            from rest_framework.exceptions import ValidationError
            raise ValidationError('Can only rate completed deliveries')
        if not delivery.rider:
            from rest_framework.exceptions import ValidationError
            raise ValidationError('This delivery has no assigned rider')
        serializer.save(customer=self.request.user, rider=delivery.rider)
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        # Get delivered orders without ratings
        delivered = Delivery.objects.filter(
            customer=request.user,
            status='DELIVERED',
            is_approved=True
        ).exclude(rating__isnull=False)
        serializer = DeliverySerializer(delivered, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='all')
    def all(self, request):
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

        ratings = Rating.objects.select_related('delivery', 'customer', 'rider').all().order_by('-created_at')
        serializer = self.get_serializer(ratings, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='low-rated-riders')
    def low_rated_riders(self, request):
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

        rider_stats = (
            Rating.objects.values('rider', 'rider__first_name', 'rider__last_name', 'rider__username')
            .annotate(
                avg_rating=Avg('rating'),
                total_ratings=Count('id'),
                low_ratings_count=Count('id', filter=Q(rating__lte=2)),
            )
            .filter(low_ratings_count__gt=0)
            .order_by('avg_rating', '-low_ratings_count')
        )

        results = []
        for stat in rider_stats:
            rider_id = stat['rider']
            full_name = f"{(stat['rider__first_name'] or '').strip()} {(stat['rider__last_name'] or '').strip()}".strip()
            rider_name = full_name or stat['rider__username'] or f'Rider #{rider_id}'

            recent = (
                Rating.objects.filter(rider_id=rider_id)
                .select_related('delivery')
                .order_by('-created_at')[:5]
            )

            results.append({
                'rider_id': rider_id,
                'rider_name': rider_name,
                'avg_rating': round(float(stat['avg_rating'] or 0), 2),
                'total_ratings': stat['total_ratings'],
                'low_ratings_count': stat['low_ratings_count'],
                'recent_ratings': [
                    {
                        'rating': item.rating,
                        'comment': item.comment or '',
                        'created_at': item.created_at,
                        'tracking_number': item.delivery.tracking_number if item.delivery else '',
                    }
                    for item in recent
                ],
            })

        return Response(results)
