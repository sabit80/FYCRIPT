"""
Basic test suite for the wallet app.

Run with:
    python manage.py test wallet

Covers the five newly-added features (password reset, transaction
PIN, money requests, admin KYC review, and the API docs endpoint
being reachable) plus the core register/login/send/exchange flows
they build on top of, so a change to shared code shows up here too.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Currency, KYC, Wallet

User = get_user_model()


class BaseAPITestCase(APITestCase):
    """Seeds the currencies every other test needs."""

    def setUp(self):
        Currency.objects.get_or_create(
            currency_name='BDT', defaults={'type': 'FIAT', 'symbol': '৳'}
        )
        Currency.objects.get_or_create(
            currency_name='USD', defaults={'type': 'FIAT', 'symbol': '$'}
        )

    def register(self, name, email, phone, password='TestPass123!'):
        response = self.client.post('/api/auth/register/', {
            'name': name, 'email': email, 'phone': phone,
            'password': password, 'confirmPassword': password,
            'preferred_currency': 'BDT',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def auth(self, access_token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")


class RegisterLoginTests(BaseAPITestCase):

    def test_register_creates_default_wallet(self):
        data = self.register('Rafi', 'rafi@example.com', '+8801700000001')
        self.assertTrue(Wallet.objects.filter(
            user__email='rafi@example.com', is_default_receive=True
        ).exists())
        self.assertIn('access', data)

    def test_login_wrong_password_rejected(self):
        self.register('Rafi', 'rafi2@example.com', '+8801700000002')
        response = self.client.post('/api/auth/login/', {
            'email': 'rafi2@example.com', 'password': 'wrong-password',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class SendExchangeTests(BaseAPITestCase):

    def setUp(self):
        super().setUp()
        self.sender = self.register('Sender', 'sender@example.com', '+8801700000010')
        self.receiver = self.register('Receiver', 'receiver@example.com', '+8801700000011')
        self.auth(self.sender['access'])
        sender_wallet = Wallet.objects.get(user__email='sender@example.com')
        sender_wallet.balance = 1000
        sender_wallet.save()
        self.sender_wallet_id = sender_wallet.wallet_id

    def test_send_by_phone(self):
        response = self.client.post('/api/send/', {
            'sender_wallet_id': self.sender_wallet_id,
            'recipient_phone': '+8801700000011',
            'amount': '100',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        receiver_wallet = Wallet.objects.get(user__email='receiver@example.com')
        self.assertEqual(receiver_wallet.balance, 100)

    def test_send_insufficient_balance_rejected(self):
        response = self.client.post('/api/send/', {
            'sender_wallet_id': self.sender_wallet_id,
            'recipient_phone': '+8801700000011',
            'amount': '999999',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TransactionPinTests(BaseAPITestCase):
    """New feature: optional PIN required before Send/Exchange."""

    def setUp(self):
        super().setUp()
        self.user = self.register('Pin User', 'pinuser@example.com', '+8801700000020')
        self.auth(self.user['access'])
        wallet = Wallet.objects.get(user__email='pinuser@example.com')
        wallet.balance = 500
        wallet.save()
        self.wallet_id = wallet.wallet_id

        self.register('Other', 'other@example.com', '+8801700000021')

    def test_set_pin_requires_correct_password(self):
        response = self.client.post('/api/profile/transaction-pin/', {
            'currentPassword': 'wrong-password', 'pin': '1234',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_blocked_without_pin_once_pin_is_set(self):
        set_response = self.client.post('/api/profile/transaction-pin/', {
            'currentPassword': 'TestPass123!', 'pin': '1234',
        }, format='json')
        self.assertEqual(set_response.status_code, status.HTTP_200_OK)

        # No PIN supplied -> rejected
        response = self.client.post('/api/send/', {
            'sender_wallet_id': self.wallet_id,
            'recipient_phone': '+8801700000021',
            'amount': '50',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Correct PIN supplied -> allowed
        response = self.client.post('/api/send/', {
            'sender_wallet_id': self.wallet_id,
            'recipient_phone': '+8801700000021',
            'amount': '50',
            'pin': '1234',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_send_unaffected_when_no_pin_ever_set(self):
        response = self.client.post('/api/send/', {
            'sender_wallet_id': self.wallet_id,
            'recipient_phone': '+8801700000021',
            'amount': '50',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


class PasswordResetTests(BaseAPITestCase):
    """New feature: forgot/reset password via emailed link."""

    def setUp(self):
        super().setUp()
        self.register('Reset Me', 'resetme@example.com', '+8801700000030')

    def test_request_reset_sends_email(self):
        response = self.client.post('/api/auth/password-reset/request/', {
            'email': 'resetme@example.com',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('resetme@example.com', mail.outbox[0].to)

    def test_request_reset_unknown_email_same_response_no_email(self):
        response = self.client.post('/api/auth/password-reset/request/', {
            'email': 'nobody@example.com',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_confirm_reset_changes_password(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = User.objects.get(email='resetme@example.com')
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = self.client.post('/api/auth/password-reset/confirm/', {
            'uid': uid, 'token': token, 'newPassword': 'BrandNewPass123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        login = self.client.post('/api/auth/login/', {
            'email': 'resetme@example.com', 'password': 'BrandNewPass123!',
        }, format='json')
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_confirm_reset_bad_token_rejected(self):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = User.objects.get(email='resetme@example.com')
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        response = self.client.post('/api/auth/password-reset/confirm/', {
            'uid': uid, 'token': 'not-a-real-token', 'newPassword': 'BrandNewPass123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class MoneyRequestTests(BaseAPITestCase):
    """New feature: Request Money (reverse of Send)."""

    def setUp(self):
        super().setUp()
        self.requester = self.register('Requester', 'requester@example.com', '+8801700000040')
        self.payer = self.register('Payer', 'payer@example.com', '+8801700000041')

        payer_wallet = Wallet.objects.get(user__email='payer@example.com')
        payer_wallet.balance = 300
        payer_wallet.save()
        self.payer_wallet_id = payer_wallet.wallet_id

    def test_create_request(self):
        self.auth(self.requester['access'])
        response = self.client.post('/api/requests/', {
            'payer_phone': '+8801700000041', 'amount': '75', 'note': 'Lunch',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], 'PENDING')
        self.assertEqual(response.data['direction'], 'OUTGOING')

    def test_payer_sees_incoming_request(self):
        self.auth(self.requester['access'])
        self.client.post('/api/requests/', {
            'payer_phone': '+8801700000041', 'amount': '75',
        }, format='json')

        self.auth(self.payer['access'])
        response = self.client.get('/api/requests/')
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['direction'], 'INCOMING')

    def test_accept_request_moves_funds(self):
        self.auth(self.requester['access'])
        create = self.client.post('/api/requests/', {
            'payer_phone': '+8801700000041', 'amount': '75',
        }, format='json')
        request_id = create.data['request_id']

        self.auth(self.payer['access'])
        response = self.client.post(f'/api/requests/{request_id}/accept/', {
            'payer_wallet_id': self.payer_wallet_id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], 'ACCEPTED')

        requester_wallet = Wallet.objects.get(user__email='requester@example.com')
        self.assertEqual(requester_wallet.balance, 75)

        payer_wallet = Wallet.objects.get(pk=self.payer_wallet_id)
        self.assertEqual(payer_wallet.balance, 225)

    def test_decline_request_moves_no_funds(self):
        self.auth(self.requester['access'])
        create = self.client.post('/api/requests/', {
            'payer_phone': '+8801700000041', 'amount': '75',
        }, format='json')
        request_id = create.data['request_id']

        self.auth(self.payer['access'])
        response = self.client.post(f'/api/requests/{request_id}/decline/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'DECLINED')

        requester_wallet = Wallet.objects.get(user__email='requester@example.com')
        self.assertEqual(requester_wallet.balance, 0)

    def test_cannot_accept_someone_elses_request(self):
        self.auth(self.requester['access'])
        create = self.client.post('/api/requests/', {
            'payer_phone': '+8801700000041', 'amount': '75',
        }, format='json')
        request_id = create.data['request_id']

        # requester tries to accept their own outgoing request -> not found
        # (query filters by payer=request.user)
        response = self.client.post(f'/api/requests/{request_id}/accept/', {
            'payer_wallet_id': self.payer_wallet_id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AdminKYCTests(BaseAPITestCase):
    """New feature: admin KYC approve/reject endpoints."""

    def setUp(self):
        super().setUp()
        self.applicant = self.register('Applicant', 'applicant@example.com', '+8801700000050')

        self.auth(self.applicant['access'])
        self.client.post('/api/kyc/', {'nid_number': '1234567890'}, format='json')

        self.admin_user = User.objects.create_superuser(
            email='admin@example.com', name='Admin', phone='+8801700000099',
            password='AdminPass123!',
        )
        admin_login = self.client.post('/api/auth/login/', {
            'email': 'admin@example.com', 'password': 'AdminPass123!',
        }, format='json')
        self.admin_access = admin_login.data['access']

    def test_non_admin_cannot_list_kyc_queue(self):
        self.auth(self.applicant['access'])
        response = self.client.get('/api/admin/kyc/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_pending_kyc(self):
        self.auth(self.admin_access)
        response = self.client.get('/api/admin/kyc/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['user_email'], 'applicant@example.com')

    def test_admin_can_approve_kyc(self):
        kyc_id = KYC.objects.get(user__email='applicant@example.com').id

        self.auth(self.admin_access)
        response = self.client.post(f'/api/admin/kyc/{kyc_id}/approve/', {
            'remarks': 'Looks good',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['verification_status'], 'APPROVED')

        kyc = KYC.objects.get(pk=kyc_id)
        self.assertEqual(kyc.reviewed_by_id, self.admin_user.id)

    def test_admin_can_reject_kyc_with_reason(self):
        kyc_id = KYC.objects.get(user__email='applicant@example.com').id

        self.auth(self.admin_access)
        response = self.client.post(f'/api/admin/kyc/{kyc_id}/reject/', {
            'remarks': 'Blurry photo',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['verification_status'], 'REJECTED')
        self.assertEqual(response.data['admin_remarks'], 'Blurry photo')


class APIDocsTests(BaseAPITestCase):
    """New feature: Swagger/OpenAPI docs are reachable without auth."""

    def test_schema_endpoint_reachable(self):
        response = self.client.get('/api/schema/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_swagger_ui_reachable(self):
        response = self.client.get('/api/docs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
