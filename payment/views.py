from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from decimal import Decimal
import random
import string

from .models import Payment, RiderWallet, WalletTransaction, WithdrawalRequest
from .serializers import PaymentSerializer, RiderWalletSerializer, WalletTransactionSerializer, WithdrawalRequestSerializer
from delivery.models import Delivery


def generate_receipt_number():
    timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
    random_str = ''.join(random.choices(string.digits, k=4))
    return f"RCP-{timestamp}-{random_str}"


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'CUSTOMER':
            return Payment.objects.filter(customer=user)
        elif user.user_type == 'RIDER':
            return Payment.objects.filter(delivery__rider=user)
        return Payment.objects.all()
    
    @action(detail=False, methods=['post'])
    def create_payment(self, request):
        """Create payment for delivery"""
        delivery_id = request.data.get('delivery_id')
        payment_method = request.data.get('payment_method')
        
        try:
            if request.user.user_type == 'RIDER':
                delivery = Delivery.objects.get(id=delivery_id, rider=request.user)
            else:
                delivery = Delivery.objects.get(id=delivery_id, customer=request.user)
        except Delivery.DoesNotExist:
            return Response({'error': 'Delivery not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if payment already exists
        if hasattr(delivery, 'payment'):
            existing = delivery.payment
            if existing.status in ('PENDING', 'COMPLETED'):
                return Response({'error': 'Payment already exists for this delivery'}, status=status.HTTP_400_BAD_REQUEST)
            # Failed payment — delete it and allow retry
            existing.delete()
        
        amount = delivery.delivery_fee
        transaction_fee = Decimal('0')
        net_amount = amount

        payment = Payment.objects.create(
            delivery=delivery,
            customer=delivery.customer,
            payment_method=payment_method,
            amount=amount,
            transaction_fee=transaction_fee,
            net_amount=net_amount,
            receipt_number=generate_receipt_number(),
            status='PENDING'
        )

        return Response({
            'payment_id': payment.id,
            'receipt_number': payment.receipt_number,
            'message': 'Payment created.',
            'amount': str(amount)
        })
    
    @action(detail=True, methods=['post'])
    def confirm_payment(self, request, pk=None):
        """Confirm payment (for COD or after online payment)"""
        payment = self.get_object()
        
        if payment.status == 'COMPLETED':
            return Response({'error': 'Payment already completed'}, status=status.HTTP_400_BAD_REQUEST)
        
        # For COD, admin/rider confirms
        if payment.payment_method == 'COD':
            if request.user.user_type in ['ADMIN', 'RIDER']:
                payment.status = 'COMPLETED'
                payment.paid_at = timezone.now()
                payment.save()
                
                # Credit rider wallet
                self._credit_rider_wallet(payment)
                
                return Response({'message': 'COD payment confirmed'})
            else:
                return Response({'error': 'Only admin or rider can confirm COD'}, status=status.HTTP_403_FORBIDDEN)
        
        return Response({'error': 'Cannot confirm payment'}, status=status.HTTP_400_BAD_REQUEST)
    
    def _credit_rider_wallet(self, payment):
        """Credit rider wallet with payment"""
        delivery = payment.delivery
        if not delivery.rider:
            return
        
        # Get or create rider wallet
        wallet, created = RiderWallet.objects.get_or_create(rider=delivery.rider)
        
        # Calculate rider earnings (net amount after fees)
        rider_earnings = payment.net_amount
        
        # Update wallet
        balance_before = wallet.balance
        wallet.balance += rider_earnings
        wallet.total_earned += rider_earnings
        wallet.save()
        
        # Create transaction record
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='EARNING',
            amount=rider_earnings,
            balance_before=balance_before,
            balance_after=wallet.balance,
            delivery=delivery,
            description=f"Earnings from delivery {delivery.tracking_number}"
        )


class RiderWalletViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RiderWalletSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'RIDER':
            return RiderWallet.objects.filter(rider=user)
        elif user.user_type == 'ADMIN':
            return RiderWallet.objects.all()
        return RiderWallet.objects.none()
    
    @action(detail=False, methods=['get'])
    def my_wallet(self, request):
        """Get current rider's wallet"""
        if request.user.user_type != 'RIDER':
            return Response({'error': 'Only riders have wallets'}, status=status.HTTP_403_FORBIDDEN)
        
        wallet, created = RiderWallet.objects.get_or_create(rider=request.user)
        serializer = self.get_serializer(wallet)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def transactions(self, request):
        """Get wallet transactions"""
        if request.user.user_type != 'RIDER':
            return Response({'error': 'Only riders have wallets'}, status=status.HTTP_403_FORBIDDEN)
        
        wallet, created = RiderWallet.objects.get_or_create(rider=request.user)
        transactions = wallet.transactions.all()[:50]  # Last 50 transactions
        serializer = WalletTransactionSerializer(transactions, many=True)
        return Response(serializer.data)


class WithdrawalRequestViewSet(viewsets.ModelViewSet):
    serializer_class = WithdrawalRequestSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'RIDER':
            return WithdrawalRequest.objects.filter(rider=user)
        elif user.user_type == 'ADMIN':
            return WithdrawalRequest.objects.all()
        return WithdrawalRequest.objects.none()
    
    def perform_create(self, serializer):
        """Create withdrawal request"""
        if self.request.user.user_type != 'RIDER':
            raise PermissionError('Only riders can request withdrawals')
        
        wallet, created = RiderWallet.objects.get_or_create(rider=self.request.user)
        amount = serializer.validated_data['amount']
        
        # Check if sufficient balance
        if wallet.balance < amount:
            raise ValueError('Insufficient balance')
        
        # Minimum withdrawal amount
        if amount < Decimal('100'):
            raise ValueError('Minimum withdrawal amount is ₱100')
        
        serializer.save(rider=self.request.user, wallet=wallet)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve withdrawal request (Admin only)"""
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Only admins can approve'}, status=status.HTTP_403_FORBIDDEN)
        
        withdrawal = self.get_object()
        
        if withdrawal.status != 'PENDING':
            return Response({'error': 'Can only approve pending requests'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Update wallet
        wallet = withdrawal.wallet
        balance_before = wallet.balance
        wallet.balance -= withdrawal.amount
        wallet.total_withdrawn += withdrawal.amount
        wallet.save()
        
        # Create transaction
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='WITHDRAWAL',
            amount=-withdrawal.amount,
            balance_before=balance_before,
            balance_after=wallet.balance,
            withdrawal_request=withdrawal,
            description=f"Withdrawal via {withdrawal.withdrawal_method}"
        )
        
        # Update withdrawal status
        withdrawal.status = 'APPROVED'
        withdrawal.processed_by = request.user
        withdrawal.processed_at = timezone.now()
        withdrawal.save()
        
        return Response({'message': 'Withdrawal approved'})
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject withdrawal request (Admin only)"""
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Only admins can reject'}, status=status.HTTP_403_FORBIDDEN)
        
        withdrawal = self.get_object()
        
        if withdrawal.status != 'PENDING':
            return Response({'error': 'Can only reject pending requests'}, status=status.HTTP_400_BAD_REQUEST)
        
        withdrawal.status = 'REJECTED'
        withdrawal.processed_by = request.user
        withdrawal.processed_at = timezone.now()
        withdrawal.admin_notes = request.data.get('reason', 'No reason provided')
        withdrawal.save()
        
        return Response({'message': 'Withdrawal rejected'})
