from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from delivery.models import Delivery
from user.models import User

from .models import Payment, RiderWallet


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
