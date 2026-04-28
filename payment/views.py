from decimal import Decimal
import random
import string

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from delivery.models import Delivery

from .models import Payment, RiderWallet, WalletTransaction, WithdrawalRequest
from .serializers import (
    PaymentSerializer,
    RiderWalletSerializer,
    WalletTransactionSerializer,
    WithdrawalRequestSerializer,
)


def generate_receipt_number():
    timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
    random_str = ''.join(random.choices(string.digits, k=4))
    return f'RCP-{timestamp}-{random_str}'


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'CUSTOMER':
            return Payment.objects.filter(customer=user)
        if user.user_type == 'RIDER':
            return Payment.objects.filter(delivery__rider=user)
        return Payment.objects.all()

    @action(detail=False, methods=['post'])
    def create_payment(self, request):
        """Create a payment record for a delivery."""
        delivery_id = request.data.get('delivery_id')
        payment_method = (request.data.get('payment_method') or '').strip().upper()
        allowed_methods = {choice for choice, _label in Payment.PAYMENT_METHOD_CHOICES}

        if payment_method not in allowed_methods:
            return Response({'error': 'Invalid payment method'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if request.user.user_type == 'RIDER':
                delivery = Delivery.objects.get(id=delivery_id, rider=request.user)
            else:
                delivery = Delivery.objects.get(id=delivery_id, customer=request.user)
        except Delivery.DoesNotExist:
            return Response({'error': 'Delivery not found'}, status=status.HTTP_404_NOT_FOUND)

        if hasattr(delivery, 'payment'):
            existing = delivery.payment
            if existing.status in ('PENDING', 'COMPLETED'):
                return Response({'error': 'Payment already exists for this delivery'}, status=status.HTTP_400_BAD_REQUEST)
            existing.delete()

        amount = delivery.delivery_fee
        payment = Payment.objects.create(
            delivery=delivery,
            customer=delivery.customer,
            payment_method=payment_method,
            amount=amount,
            transaction_fee=Decimal('0'),
            net_amount=amount,
            receipt_number=generate_receipt_number(),
            status='PENDING',
        )

        return Response(
            {
                'payment_id': payment.id,
                'receipt_number': payment.receipt_number,
                'message': 'Payment created.',
                'amount': str(amount),
            }
        )

    @action(detail=True, methods=['post'])
    def confirm_payment(self, request, pk=None):
        """Confirm a COD or GCash payment once the collection evidence is complete."""
        payment = self.get_object()
        delivery = payment.delivery

        if payment.status == 'COMPLETED':
            return Response({'error': 'Payment already completed'}, status=status.HTTP_400_BAD_REQUEST)

        is_admin = request.user.user_type == 'ADMIN'
        is_assigned_rider = request.user.user_type == 'RIDER' and delivery.rider_id == request.user.id
        if not (is_admin or is_assigned_rider):
            return Response(
                {'error': 'Only the assigned rider or an admin can confirm payment'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if payment.payment_method == 'GCASH' and not delivery.gcash_proof:
            return Response(
                {'error': 'GCash proof is required before confirming payment'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if payment.payment_method not in {'COD', 'GCASH'}:
            return Response(
                {'error': f'{payment.payment_method} payments cannot be confirmed from this action'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment.status = 'COMPLETED'
        payment.paid_at = timezone.now()
        payment.save(update_fields=['status', 'paid_at'])

        self._credit_rider_wallet(payment)

        method_label = 'GCash' if payment.payment_method == 'GCASH' else 'COD'
        return Response({'message': f'{method_label} payment confirmed'})

    def _credit_rider_wallet(self, payment):
        """Credit the assigned rider wallet after a payment is finalized."""
        delivery = payment.delivery
        if not delivery.rider:
            return

        wallet, _created = RiderWallet.objects.get_or_create(rider=delivery.rider)
        rider_earnings = payment.net_amount
        balance_before = wallet.balance
        wallet.balance += rider_earnings
        wallet.total_earned += rider_earnings
        wallet.save(update_fields=['balance', 'total_earned', 'updated_at'])

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='EARNING',
            amount=rider_earnings,
            balance_before=balance_before,
            balance_after=wallet.balance,
            delivery=delivery,
            description=f'Earnings from delivery {delivery.tracking_number}',
        )


class RiderWalletViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RiderWalletSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'RIDER':
            return RiderWallet.objects.filter(rider=user)
        if user.user_type == 'ADMIN':
            return RiderWallet.objects.all()
        return RiderWallet.objects.none()

    @action(detail=False, methods=['get'])
    def my_wallet(self, request):
        """Get current rider wallet."""
        if request.user.user_type != 'RIDER':
            return Response({'error': 'Only riders have wallets'}, status=status.HTTP_403_FORBIDDEN)

        wallet, _created = RiderWallet.objects.get_or_create(rider=request.user)
        serializer = self.get_serializer(wallet)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def transactions(self, request):
        """Get wallet transactions."""
        if request.user.user_type != 'RIDER':
            return Response({'error': 'Only riders have wallets'}, status=status.HTTP_403_FORBIDDEN)

        wallet, _created = RiderWallet.objects.get_or_create(rider=request.user)
        transactions = wallet.transactions.select_related('delivery').all()[:50]
        serializer = WalletTransactionSerializer(transactions, many=True)
        return Response(serializer.data)


class WithdrawalRequestViewSet(viewsets.ModelViewSet):
    serializer_class = WithdrawalRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'RIDER':
            return WithdrawalRequest.objects.filter(rider=user)
        if user.user_type == 'ADMIN':
            return WithdrawalRequest.objects.all()
        return WithdrawalRequest.objects.none()

    def perform_create(self, serializer):
        """Create a withdrawal request."""
        if self.request.user.user_type != 'RIDER':
            raise PermissionDenied('Only riders can request withdrawals')

        wallet, _created = RiderWallet.objects.get_or_create(rider=self.request.user)
        amount = serializer.validated_data['amount']

        if amount < Decimal('100'):
            raise ValidationError({'amount': 'Minimum withdrawal amount is ₱100'})
        if wallet.balance < amount:
            raise ValidationError({'amount': 'Insufficient balance'})

        serializer.save(rider=self.request.user, wallet=wallet)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a withdrawal request (Admin only)."""
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Only admins can approve'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().select_related('wallet').get(pk=self.get_object().pk)
            if withdrawal.status != 'PENDING':
                return Response({'error': 'Can only approve pending requests'}, status=status.HTTP_400_BAD_REQUEST)

            wallet = RiderWallet.objects.select_for_update().get(pk=withdrawal.wallet_id)
            if wallet.balance < withdrawal.amount:
                return Response(
                    {'error': 'Cannot approve withdrawal because the rider wallet no longer has enough balance'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            balance_before = wallet.balance
            wallet.balance -= withdrawal.amount
            wallet.total_withdrawn += withdrawal.amount
            wallet.save(update_fields=['balance', 'total_withdrawn', 'updated_at'])

            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='WITHDRAWAL',
                amount=-withdrawal.amount,
                balance_before=balance_before,
                balance_after=wallet.balance,
                withdrawal_request=withdrawal,
                description=f'Withdrawal via {withdrawal.withdrawal_method}',
            )

            withdrawal.status = 'APPROVED'
            withdrawal.processed_by = request.user
            withdrawal.processed_at = timezone.now()
            withdrawal.save(update_fields=['status', 'processed_by', 'processed_at'])

        return Response({'message': 'Withdrawal approved'})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a withdrawal request (Admin only)."""
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Only admins can reject'}, status=status.HTTP_403_FORBIDDEN)

        withdrawal = self.get_object()
        if withdrawal.status != 'PENDING':
            return Response({'error': 'Can only reject pending requests'}, status=status.HTTP_400_BAD_REQUEST)

        withdrawal.status = 'REJECTED'
        withdrawal.processed_by = request.user
        withdrawal.processed_at = timezone.now()
        withdrawal.admin_notes = request.data.get('reason', 'No reason provided')
        withdrawal.save(update_fields=['status', 'processed_by', 'processed_at', 'admin_notes'])

        return Response({'message': 'Withdrawal rejected'})
