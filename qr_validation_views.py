# Add these views to delivery/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import Delivery, QRScanLog
from user.models import User

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_qr_scan(request):
    """
    Validate QR code scan with security checks
    """
    tracking_number = request.data.get('tracking_number')
    scan_type = request.data.get('scan_type')  # PICKUP or DELIVERY
    latitude = request.data.get('latitude')
    longitude = request.data.get('longitude')
    
    if not tracking_number or not scan_type:
        return Response({
            'valid': False,
            'error': 'Missing required fields'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        delivery = Delivery.objects.get(tracking_number=tracking_number)
    except Delivery.DoesNotExist:
        # Log invalid scan attempt
        QRScanLog.objects.create(
            delivery=None,
            scanned_by=request.user,
            scan_type=scan_type,
            status_before='UNKNOWN',
            status_after='UNKNOWN',
            is_valid=False,
            validation_error='Delivery not found',
            latitude=latitude,
            longitude=longitude
        )
        return Response({
            'valid': False,
            'error': 'Invalid tracking number'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Validate scan type
    if scan_type == 'PICKUP':
        # Check if rider is online
        if not request.user.is_online:
            QRScanLog.objects.create(
                delivery=delivery,
                scanned_by=request.user,
                scan_type=scan_type,
                status_before=delivery.status,
                status_after=delivery.status,
                is_valid=False,
                validation_error='Rider is offline',
                latitude=latitude,
                longitude=longitude
            )
            return Response({
                'valid': False,
                'error': 'You must be online to pick up packages'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if delivery is in correct status
        if delivery.status != 'PENDING':
            QRScanLog.objects.create(
                delivery=delivery,
                scanned_by=request.user,
                scan_type=scan_type,
                status_before=delivery.status,
                status_after=delivery.status,
                is_valid=False,
                validation_error=f'Invalid status for pickup: {delivery.status}',
                latitude=latitude,
                longitude=longitude
            )
            return Response({
                'valid': False,
                'error': f'Package already picked up. Current status: {delivery.status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user is the assigned rider
        if delivery.rider != request.user:
            QRScanLog.objects.create(
                delivery=delivery,
                scanned_by=request.user,
                scan_type=scan_type,
                status_before=delivery.status,
                status_after=delivery.status,
                is_valid=False,
                validation_error='Not assigned rider',
                latitude=latitude,
                longitude=longitude
            )
            return Response({
                'valid': False,
                'error': 'This delivery is not assigned to you'
            }, status=status.HTTP_403_FORBIDDEN)
    
    elif scan_type == 'DELIVERY':
        # Check if delivery is in correct status
        if delivery.status not in ['PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY']:
            QRScanLog.objects.create(
                delivery=delivery,
                scanned_by=request.user,
                scan_type=scan_type,
                status_before=delivery.status,
                status_after=delivery.status,
                is_valid=False,
                validation_error=f'Invalid status for delivery: {delivery.status}',
                latitude=latitude,
                longitude=longitude
            )
            return Response({
                'valid': False,
                'error': f'Cannot complete delivery. Current status: {delivery.status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user is the assigned rider
        if delivery.rider != request.user:
            QRScanLog.objects.create(
                delivery=delivery,
                scanned_by=request.user,
                scan_type=scan_type,
                status_before=delivery.status,
                status_after=delivery.status,
                is_valid=False,
                validation_error='Not assigned rider',
                latitude=latitude,
                longitude=longitude
            )
            return Response({
                'valid': False,
                'error': 'This delivery is not assigned to you'
            }, status=status.HTTP_403_FORBIDDEN)
    
    # Log valid scan
    status_after = 'PICKED_UP' if scan_type == 'PICKUP' else 'DELIVERED'
    QRScanLog.objects.create(
        delivery=delivery,
        scanned_by=request.user,
        scan_type=scan_type,
        status_before=delivery.status,
        status_after=status_after,
        is_valid=True,
        latitude=latitude,
        longitude=longitude
    )
    
    return Response({
        'valid': True,
        'delivery': {
            'id': delivery.id,
            'tracking_number': delivery.tracking_number,
            'sender_name': delivery.sender_name,
            'receiver_name': delivery.receiver_name,
            'delivery_address': delivery.delivery_address,
            'status': delivery.status,
            'delivery_fee': str(delivery.delivery_fee)
        }
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_scan_history(request):
    """
    Get QR scan history for the authenticated user
    """
    user = request.user
    
    if user.user_type == 'ADMIN':
        # Admin can see all scans
        scans = QRScanLog.objects.all()[:100]  # Limit to last 100
    elif user.user_type == 'RIDER':
        # Rider can see their own scans
        scans = QRScanLog.objects.filter(scanned_by=user)[:50]
    else:
        # Customer can see scans for their deliveries
        scans = QRScanLog.objects.filter(delivery__customer=user)[:50]
    
    scan_data = []
    for scan in scans:
        scan_data.append({
            'id': scan.id,
            'tracking_number': scan.delivery.tracking_number if scan.delivery else 'N/A',
            'scan_type': scan.scan_type,
            'scanned_by': scan.scanned_by.get_full_name() if scan.scanned_by else 'Unknown',
            'scanned_at': scan.scanned_at.isoformat(),
            'status_before': scan.status_before,
            'status_after': scan.status_after,
            'is_valid': scan.is_valid,
            'location': scan.location_address,
            'validation_error': scan.validation_error
        })
    
    return Response({
        'count': len(scan_data),
        'scans': scan_data
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_delivery_scan_history(request, tracking_number):
    """
    Get scan history for a specific delivery
    """
    try:
        delivery = Delivery.objects.get(tracking_number=tracking_number)
        
        # Check permissions
        user = request.user
        if user.user_type == 'CUSTOMER' and delivery.customer != user:
            return Response({
                'error': 'Not authorized'
            }, status=status.HTTP_403_FORBIDDEN)
        
        scans = QRScanLog.objects.filter(delivery=delivery)
        
        scan_data = []
        for scan in scans:
            scan_data.append({
                'id': scan.id,
                'scan_type': scan.scan_type,
                'scanned_by': scan.scanned_by.get_full_name() if scan.scanned_by else 'Unknown',
                'scanned_at': scan.scanned_at.isoformat(),
                'status_before': scan.status_before,
                'status_after': scan.status_after,
                'is_valid': scan.is_valid,
                'location': scan.location_address
            })
        
        return Response({
            'tracking_number': tracking_number,
            'scan_count': len(scan_data),
            'scans': scan_data
        })
        
    except Delivery.DoesNotExist:
        return Response({
            'error': 'Delivery not found'
        }, status=status.HTTP_404_NOT_FOUND)
