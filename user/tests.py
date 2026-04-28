from django.test import TestCase
from rest_framework.test import APIClient

from .models import User


class UserListPermissionsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin_users',
            email='admin_users@example.com',
            password='testpass123',
            user_type='ADMIN',
            is_approved=True,
            is_email_verified=True,
        )
        self.customer = User.objects.create_user(
            username='customer_users',
            email='customer_users@example.com',
            password='testpass123',
            user_type='CUSTOMER',
            is_approved=True,
            is_email_verified=True,
        )

    def test_user_list_requires_authentication(self):
        response = self.client.get('/api/auth/users/')

        self.assertEqual(response.status_code, 401)

    def test_non_admin_cannot_access_user_list(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.get('/api/auth/users/')

        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_user_list(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get('/api/auth/users/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
