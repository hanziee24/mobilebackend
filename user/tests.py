import base64
import os
import shutil
from unittest.mock import patch

from django.test import TestCase
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from .email_utils import build_email_diagnostics, get_system_from_email
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


class EmailUtilsTests(TestCase):
    @override_settings(
        DEFAULT_FROM_EMAIL='',
        SUPPORT_TICKET_EMAIL='support@example.com',
        EMAIL_HOST='smtp-relay.brevo.com',
        EMAIL_HOST_USER='mailer@example.com',
        EMAIL_HOST_PASSWORD='secret',
        EMAIL_TIMEOUT=30,
    )
    def test_get_system_from_email_falls_back_to_support_email(self):
        self.assertEqual(get_system_from_email(), 'support@example.com')

    @override_settings(
        DEFAULT_FROM_EMAIL='deliverytrack2026@gmail.com',
        SUPPORT_TICKET_EMAIL='support@example.com',
        EMAIL_HOST='smtp-relay.brevo.com',
        EMAIL_HOST_USER='mailer@example.com',
        EMAIL_HOST_PASSWORD='secret',
        EMAIL_TIMEOUT=30,
        EMAIL_PORT=587,
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
    )
    def test_build_email_diagnostics_flags_unverified_brevo_sender_risk(self):
        diagnostics = build_email_diagnostics()

        self.assertEqual(diagnostics['from_email'], 'deliverytrack2026@gmail.com')
        self.assertIn(
            'Brevo may reject Gmail sender addresses unless that exact sender is verified in Brevo.',
            diagnostics['warnings'],
        )


class ForgotPasswordEmailErrorTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='forgot_pw_user',
            email='forgot_pw@example.com',
            password='Testpass123!',
            user_type='CUSTOMER',
            is_approved=True,
            is_email_verified=True,
        )

    @override_settings(DEBUG=True)
    @patch('user.views.send_system_email', side_effect=Exception('550 Sender address rejected'))
    def test_forgot_password_returns_real_mail_error_in_debug(self, _mock_send):
        response = self.client.post('/api/auth/forgot-password/', {'email': self.user.email}, format='json')

        self.assertEqual(response.status_code, 500)
        self.assertIn('Failed to send reset code. Please try again.', response.data['error'])
        self.assertIn('550 Sender address rejected', response.data['error'])


TEST_MEDIA_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'test_media')
os.makedirs(TEST_MEDIA_ROOT, exist_ok=True)

TEST_STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, STORAGES=TEST_STORAGES)
class UserProfileGcashQrTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.cashier = User.objects.create_user(
            username='cashier_qr',
            email='cashier_qr@example.com',
            password='testpass123',
            user_type='CASHIER',
            is_approved=True,
            is_email_verified=True,
        )
        self.client.force_authenticate(user=self.cashier)

    def _sample_qr(self):
        return SimpleUploadedFile(
            'gcash_qr.gif',
            base64.b64decode(
                'R0lGODdhAQABAIABAP///wAAACwAAAAAAQABAAACAkQBADs='
            ),
            content_type='image/gif',
        )

    def test_cashier_can_upload_gcash_qr_from_profile(self):
        response = self.client.patch(
            '/api/auth/profile/',
            {'gcash_qr': self._sample_qr()},
            format='multipart',
        )

        self.assertEqual(response.status_code, 200)
        self.cashier.refresh_from_db()
        self.assertTrue(bool(self.cashier.gcash_qr))
        self.assertTrue(self.cashier.gcash_qr.name.startswith('gcash_qr/'))
        self.assertTrue(response.data['gcash_qr'].startswith('http://testserver/'))

    def test_cashier_can_remove_gcash_qr_from_profile(self):
        self.cashier.gcash_qr.save('existing_qr.png', self._sample_qr(), save=True)

        response = self.client.patch(
            '/api/auth/profile/',
            {'gcash_qr': ''},
            format='multipart',
        )

        self.assertEqual(response.status_code, 200)
        self.cashier.refresh_from_db()
        self.assertFalse(bool(self.cashier.gcash_qr))
        self.assertIsNone(response.data['gcash_qr'])
