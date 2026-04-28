from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from delivery.models import Delivery
from user.models import User

from .models import Payment, RiderWallet, WithdrawalRequest


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            username='customer_payment',
            email='customer_payment@example.com',
            password='testpass123',
            user_type='CUSTOMER',
            is_approved=True,
            is_email_verified=True,
        )
        self.rider = User.objects.create_user(
            username='rider_payment',
            email='rider_payment@example.com',
            password='testpass123',
            user_type='RIDER',
            is_approved=True,
            is_online=True,
            is_email_verified=True,
        )
        self.delivery = Delivery.objects.create(
            tracking_number='TRK-PAY-0001',
            customer=self.customer,
            rider=self.rider,
            pickup_address='Pickup',
            delivery_address='Dropoff',
            delivery_fee=Decimal('150.00'),
            is_approved=True,
        )

    def test_rider_can_confirm_gcash_payment_with_uploaded_proof(self):
        payment = Payment.objects.create(
            delivery=self.delivery,
            customer=self.customer,
            payment_method='GCASH',
            amount=Decimal('150.00'),
            transaction_fee=Decimal('0.00'),
            net_amount=Decimal('150.00'),
            receipt_number='RCP-TEST-0001',
            status='PENDING',
        )
        self.delivery.gcash_proof = 'gcash_proofs/sample.jpg'
        self.delivery.save(update_fields=['gcash_proof'])
        self.client.force_authenticate(user=self.rider)

        response = self.client.post(f'/api/payment/payments/{payment.id}/confirm_payment/')

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'COMPLETED')
        wallet = RiderWallet.objects.get(rider=self.rider)
        self.assertEqual(wallet.balance, Decimal('150.00'))

    def test_gcash_confirmation_requires_uploaded_proof(self):
        payment = Payment.objects.create(
            delivery=self.delivery,
            customer=self.customer,
            payment_method='GCASH',
            amount=Decimal('150.00'),
            transaction_fee=Decimal('0.00'),
            net_amount=Decimal('150.00'),
            receipt_number='RCP-TEST-0002',
            status='PENDING',
        )
        self.client.force_authenticate(user=self.rider)

        response = self.client.post(f'/api/payment/payments/{payment.id}/confirm_payment/')

        self.assertEqual(response.status_code, 400)
        self.assertIn('proof', response.data['error'].lower())


class WithdrawalApprovalTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin_withdraw',
            email='admin_withdraw@example.com',
            password='testpass123',
            user_type='ADMIN',
            is_approved=True,
            is_email_verified=True,
        )
        self.rider = User.objects.create_user(
            username='rider_withdraw',
            email='rider_withdraw@example.com',
            password='testpass123',
            user_type='RIDER',
            is_approved=True,
            is_online=True,
            is_email_verified=True,
        )
        self.wallet = RiderWallet.objects.create(
            rider=self.rider,
            balance=Decimal('120.00'),
            total_earned=Decimal('120.00'),
        )

    def test_withdrawal_create_returns_validation_error_instead_of_server_error(self):
        self.client.force_authenticate(user=self.rider)

        response = self.client.post(
            '/api/payment/withdrawals/',
            {
                'amount': '90.00',
                'withdrawal_method': 'GCASH',
                'account_name': 'Rider One',
                'account_number': '09123456789',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Minimum withdrawal amount', str(response.data))

    def test_approve_rejects_when_wallet_balance_is_no_longer_enough(self):
        withdrawal = WithdrawalRequest.objects.create(
            rider=self.rider,
            wallet=self.wallet,
            amount=Decimal('110.00'),
            withdrawal_method='GCASH',
            account_name='Rider One',
            account_number='09123456789',
            status='PENDING',
        )
        self.wallet.balance = Decimal('50.00')
        self.wallet.save(update_fields=['balance'])
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(f'/api/payment/withdrawals/{withdrawal.id}/approve/')

        self.assertEqual(response.status_code, 400)
        self.assertIn('no longer has enough balance', response.data['error'])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('50.00'))
