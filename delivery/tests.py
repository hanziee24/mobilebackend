from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch

from delivery.models import Delivery, DeliveryRequest
from delivery.views import auto_assign_rider
from user.models import User, Branch


class TrackingAndStatusTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            username='customer1',
            email='customer1@example.com',
            password='testpass123',
            user_type='CUSTOMER',
            is_approved=True,
            is_email_verified=True,
        )
        self.rider = User.objects.create_user(
            username='rider1',
            email='rider1@example.com',
            password='testpass123',
            user_type='RIDER',
            first_name='Rider',
            last_name='One',
            is_approved=True,
            is_online=True,
            is_email_verified=True,
        )

    def _create_delivery(self, status='PENDING'):
        return Delivery.objects.create(
            tracking_number='TRK-1234567890',
            customer=self.customer,
            rider=self.rider,
            pickup_address='Warehouse A, District 5, Metro City',
            delivery_address='Customer Address, Block 12, Metro City',
            status=status,
            is_approved=True,
        )

    def test_track_by_number_is_case_insensitive(self):
        self._create_delivery()

        response = self.client.get('/api/track/trk-1234567890/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['tracking_number'], 'TRK-1234567890')

    def test_track_by_number_masks_sensitive_fields(self):
        self._create_delivery()

        response = self.client.get('/api/track/TRK-1234567890/')

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data['pickup_address'], 'Warehouse A, District 5, Metro City')
        self.assertNotEqual(response.data['delivery_address'], 'Customer Address, Block 12, Metro City')
        self.assertEqual(response.data['rider_name'], 'Rider O.')

    def test_update_status_rejects_invalid_transition_for_rider(self):
        delivery = self._create_delivery(status='PENDING')
        self.client.force_authenticate(user=self.rider)

        response = self.client.post(f'/api/deliveries/{delivery.id}/update_status/', {'status': 'IN_TRANSIT'})

        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid transition', response.data['error'])

    def test_update_status_requires_failure_reason(self):
        delivery = self._create_delivery(status='IN_TRANSIT')
        self.client.force_authenticate(user=self.rider)

        response = self.client.post(f'/api/deliveries/{delivery.id}/update_status/', {'status': 'FAILED'})

        self.assertEqual(response.status_code, 400)
        self.assertIn('failure_reason', response.data['error'])

    def test_update_status_allows_valid_transition(self):
        delivery = self._create_delivery(status='PENDING')
        self.client.force_authenticate(user=self.rider)

        response = self.client.post(f'/api/deliveries/{delivery.id}/update_status/', {'status': 'picked_up'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'PICKED_UP')


class AutoAssignRiderTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username='customer_zone',
            email='customer_zone@example.com',
            password='testpass123',
            user_type='CUSTOMER',
            is_approved=True,
            is_email_verified=True,
        )
        self.branch_a = Branch.objects.create(name='North Hub', address='North', latitude=14.600000, longitude=121.000000)
        self.branch_b = Branch.objects.create(name='South Hub', address='South', latitude=14.500000, longitude=121.050000)
        self.customer.branch = self.branch_a
        self.customer.save(update_fields=['branch'])

    def _create_rider(self, username, email, branch=None, lat=None, lng=None):
        return User.objects.create_user(
            username=username,
            email=email,
            password='testpass123',
            user_type='RIDER',
            is_approved=True,
            is_online=True,
            is_available=True,
            is_email_verified=True,
            branch=branch,
            current_latitude=lat,
            current_longitude=lng,
        )

    def _create_delivery(self, tracking_number, pickup_address='Pickup|14.600000,121.000000'):
        return Delivery.objects.create(
            tracking_number=tracking_number,
            customer=self.customer,
            pickup_address=pickup_address,
            delivery_address='Dropoff',
            status='PENDING',
            is_approved=True,
        )

    def test_auto_assign_prioritizes_same_branch_category(self):
        in_zone = self._create_rider('rider_zone', 'rider_zone@example.com', branch=self.branch_a, lat=14.650000, lng=121.020000)
        self._create_rider('rider_other', 'rider_other@example.com', branch=self.branch_b, lat=14.600100, lng=121.000100)
        delivery = self._create_delivery('TRK-2000000001')

        selected = auto_assign_rider(delivery)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.id, in_zone.id)

    def test_auto_assign_returns_none_when_no_rider_in_same_branch(self):
        # Customer belongs to branch_a, but only branch_b riders are online/available.
        self._create_rider('rider_other_only', 'rider_other_only@example.com', branch=self.branch_b, lat=14.600100, lng=121.000100)
        delivery = self._create_delivery('TRK-2000000099')

        selected = auto_assign_rider(delivery)

        self.assertIsNone(selected)

    def test_auto_assign_selects_nearest_when_branch_not_available(self):
        self.customer.branch = None
        self.customer.save(update_fields=['branch'])

        far_rider = self._create_rider('rider_far', 'rider_far@example.com', branch=self.branch_b, lat=14.700000, lng=121.100000)
        near_rider = self._create_rider('rider_near', 'rider_near@example.com', branch=self.branch_a, lat=14.600050, lng=121.000050)
        delivery = Delivery.objects.create(
            tracking_number='TRK-2000000002',
            customer=self.customer,
            pickup_address='Pickup|14.600000,121.000000',
            delivery_address='Dropoff Near North Hub|14.600000,121.000000',
            status='PENDING',
            is_approved=True,
        )

        selected = auto_assign_rider(delivery)

        self.assertIsNotNone(selected)
        self.assertNotEqual(selected.id, far_rider.id)
        self.assertEqual(selected.id, near_rider.id)

    def test_auto_assign_uses_workload_tiebreaker(self):
        self.customer.branch = None
        self.customer.save(update_fields=['branch'])

        busy_rider = self._create_rider('rider_busy', 'rider_busy@example.com', lat=14.600100, lng=121.000100)
        free_rider = self._create_rider('rider_free', 'rider_free@example.com', lat=14.600100, lng=121.000100)

        Delivery.objects.create(
            tracking_number='TRK-2000000003',
            customer=self.customer,
            rider=busy_rider,
            pickup_address='BusyPickup',
            delivery_address='BusyDrop',
            status='IN_TRANSIT',
            is_approved=True,
        )
        delivery = self._create_delivery('TRK-2000000004')

        selected = auto_assign_rider(delivery)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.id, free_rider.id)


class RiderAssignmentValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin_assign',
            email='admin_assign@example.com',
            password='testpass123',
            user_type='ADMIN',
            is_approved=True,
            is_email_verified=True,
        )
        self.customer = User.objects.create_user(
            username='customer_assign',
            email='customer_assign@example.com',
            password='testpass123',
            user_type='CUSTOMER',
            is_approved=True,
            is_email_verified=True,
        )
        self.branch = Branch.objects.create(
            name='Basak Hub',
            address='Basak, Cebu City',
            latitude=10.297500,
            longitude=123.894100,
        )
        self.rider = User.objects.create_user(
            username='ralph_assign',
            email='ralph_assign@example.com',
            password='testpass123',
            user_type='RIDER',
            is_approved=True,
            is_online=True,
            is_available=True,
            is_email_verified=True,
            branch=self.branch,
        )
        self.other_branch = Branch.objects.create(
            name='Mandaue Hub',
            address='Mandaue City',
            latitude=10.337800,
            longitude=123.922900,
        )
        self.other_branch_rider = User.objects.create_user(
            username='other_branch_rider',
            email='other_branch_rider@example.com',
            password='testpass123',
            user_type='RIDER',
            is_approved=True,
            is_online=True,
            is_available=True,
            is_email_verified=True,
            branch=self.other_branch,
        )
        self.customer.branch = self.branch
        self.customer.save(update_fields=['branch'])
        self.client.force_authenticate(user=self.admin)

    def test_manual_assignment_rejects_when_delivery_has_no_coordinates(self):
        delivery = Delivery.objects.create(
            tracking_number='TRK-3000000001',
            customer=self.customer,
            pickup_address='Branch Drop-off',
            delivery_address='Mandaue City Proper',
            status='PENDING',
            is_approved=True,
        )

        response = self.client.patch(
            f'/api/deliveries/{delivery.id}/',
            {'rider': self.rider.id},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('no map pin', response.data['error'].lower())

    def test_manual_assignment_allows_when_delivery_has_coordinates_in_range(self):
        delivery = Delivery.objects.create(
            tracking_number='TRK-3000000002',
            customer=self.customer,
            pickup_address='Branch Drop-off',
            delivery_address='Near Basak|10.305000,123.902000',
            status='PENDING',
            is_approved=True,
        )

        response = self.client.patch(
            f'/api/deliveries/{delivery.id}/',
            {'rider': self.rider.id},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('rider'), self.rider.id)

    def test_manual_assignment_rejects_when_rider_not_in_same_hub(self):
        delivery = Delivery.objects.create(
            tracking_number='TRK-3000000003',
            customer=self.customer,
            pickup_address='Branch Drop-off',
            delivery_address='Near Basak|10.305000,123.902000',
            status='PENDING',
            is_approved=True,
        )

        response = self.client.patch(
            f'/api/deliveries/{delivery.id}/',
            {'rider': self.other_branch_rider.id},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('outside rider', response.data['error'].lower())

    def test_approve_does_not_auto_assign_when_delivery_has_no_coordinates(self):
        delivery = Delivery.objects.create(
            tracking_number='TRK-3000000004',
            customer=self.customer,
            pickup_address='Branch Drop-off|10.297500,123.894100',
            delivery_address='Mandaue City Proper',
            status='PENDING',
            is_approved=False,
        )

        response = self.client.post(f'/api/deliveries/{delivery.id}/approve/')

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data.get('rider_assigned'))
        delivery.refresh_from_db()
        self.assertTrue(delivery.is_approved)
        self.assertIsNone(delivery.rider)

    def test_approve_does_not_auto_assign_when_rider_hub_is_too_far(self):
        delivery = Delivery.objects.create(
            tracking_number='TRK-3000000005',
            customer=self.customer,
            pickup_address='Branch Drop-off|10.297500,123.894100',
            delivery_address='Far Delivery|11.000000,123.894100',
            status='PENDING',
            is_approved=False,
        )

        response = self.client.post(f'/api/deliveries/{delivery.id}/approve/')

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data.get('rider_assigned'))
        delivery.refresh_from_db()
        self.assertTrue(delivery.is_approved)
        self.assertIsNone(delivery.rider)

    def test_manual_assignment_allows_forwarding_to_nearest_hub(self):
        # Customer default hub is Basak, but delivery is much closer to Mandaue Hub.
        delivery = Delivery.objects.create(
            tracking_number='TRK-3000000006',
            customer=self.customer,
            pickup_address='Branch Drop-off',
            delivery_address='Near Mandaue|10.337700,123.923000',
            status='PENDING',
            is_approved=True,
        )

        response = self.client.patch(
            f'/api/deliveries/{delivery.id}/',
            {'rider': self.other_branch_rider.id},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('rider'), self.other_branch_rider.id)


class DeliveryRequestVisibilityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            username='customer_requests',
            email='customer_requests@example.com',
            password='testpass123',
            user_type='CUSTOMER',
            is_approved=True,
            is_email_verified=True,
        )
        self.other_customer = User.objects.create_user(
            username='other_customer_requests',
            email='other_customer_requests@example.com',
            password='testpass123',
            user_type='CUSTOMER',
            is_approved=True,
            is_email_verified=True,
        )
        self.cashier = User.objects.create_user(
            username='cashier_requests',
            email='cashier_requests@example.com',
            password='testpass123',
            user_type='CASHIER',
            is_approved=True,
            is_email_verified=True,
        )

    def test_customer_can_list_own_pending_delivery_requests(self):
        own_pending = DeliveryRequest.objects.create(
            customer=self.customer,
            sender_name='Sender One',
            sender_contact='09123456789',
            sender_address='Sender Address',
            receiver_name='Receiver One',
            receiver_contact='09987654321',
            receiver_address='Receiver Address',
            item_type='Documents',
            weight='1',
            quantity='1',
            status='PENDING',
        )
        DeliveryRequest.objects.create(
            customer=self.customer,
            sender_name='Sender Three',
            sender_contact='09123456781',
            sender_address='Sender Address',
            receiver_name='Receiver Three',
            receiver_contact='09987654322',
            receiver_address='Receiver Address',
            item_type='Parcel',
            weight='3',
            quantity='1',
            status='CANCELLED',
        )
        DeliveryRequest.objects.create(
            customer=self.other_customer,
            sender_name='Sender Other',
            sender_contact='09123456782',
            sender_address='Sender Address',
            receiver_name='Receiver Other',
            receiver_contact='09987654323',
            receiver_address='Receiver Address',
            item_type='Parcel',
            weight='4',
            quantity='1',
            status='PENDING',
        )

        self.client.force_authenticate(user=self.customer)
        response = self.client.get('/api/delivery-requests/')

        self.assertEqual(response.status_code, 200)
        returned_ids = {item['id'] for item in response.data}
        self.assertEqual(returned_ids, {own_pending.id})

    def test_customer_cannot_cancel_another_customers_request(self):
        foreign_request = DeliveryRequest.objects.create(
            customer=self.other_customer,
            sender_name='Sender Other',
            sender_contact='09123456782',
            sender_address='Sender Address',
            receiver_name='Receiver Other',
            receiver_contact='09987654323',
            receiver_address='Receiver Address',
            item_type='Parcel',
            weight='4',
            quantity='1',
            status='PENDING',
        )

        self.client.force_authenticate(user=self.customer)
        response = self.client.post(f'/api/delivery-requests/{foreign_request.id}/cancel/')

        self.assertEqual(response.status_code, 403)

    def test_cashier_only_sees_pending_delivery_requests(self):
        pending_request = DeliveryRequest.objects.create(
            customer=self.customer,
            sender_name='Sender One',
            sender_contact='09123456789',
            sender_address='Sender Address',
            receiver_name='Receiver One',
            receiver_contact='09987654321',
            receiver_address='Receiver Address',
            item_type='Documents',
            weight='1',
            quantity='1',
            status='PENDING',
        )
        DeliveryRequest.objects.create(
            customer=self.customer,
            sender_name='Sender Two',
            sender_contact='09123456780',
            sender_address='Sender Address',
            receiver_name='Receiver Two',
            receiver_contact='09987654320',
            receiver_address='Receiver Address',
            item_type='Parcel',
            weight='2',
            quantity='1',
            status='ACCEPTED',
        )

        self.client.force_authenticate(user=self.cashier)
        response = self.client.get('/api/delivery-requests/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], pending_request.id)


class DeliveryRequestCreateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            username='customer_create_request',
            email='customer_create_request@example.com',
            password='testpass123',
            user_type='CUSTOMER',
            is_approved=True,
            is_email_verified=True,
        )
        self.cashier = User.objects.create_user(
            username='cashier_create_request',
            email='cashier_create_request@example.com',
            password='testpass123',
            user_type='CASHIER',
            is_approved=True,
            is_email_verified=True,
        )
        self.payload = {
            'sender_name': 'Sender One',
            'sender_contact': '09123456789',
            'sender_address': 'Sender Address',
            'receiver_name': 'Receiver One',
            'receiver_contact': '09987654321',
            'receiver_address': 'Receiver Address',
            'item_type': 'Laptop',
            'weight': '1.000',
            'quantity': '2',
            'is_fragile': 'true',
            'preferred_payment_method': 'CASH',
        }

    def test_customer_can_create_delivery_request(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.post('/api/delivery-requests/create/', self.payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(DeliveryRequest.objects.count(), 1)
        saved_request = DeliveryRequest.objects.get()
        self.assertEqual(saved_request.customer_id, self.customer.id)
        self.assertEqual(saved_request.sender_address, 'Sender Address')
        self.assertEqual(saved_request.preferred_payment_method, 'CASH')

    def test_delivery_request_still_succeeds_when_notification_creation_fails(self):
        self.client.force_authenticate(user=self.customer)

        with patch('delivery.views.Notification.objects.create', side_effect=Exception('notification failure')):
            response = self.client.post('/api/delivery-requests/create/', self.payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(DeliveryRequest.objects.count(), 1)
