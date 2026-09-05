from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import (
    Wallet, Transaction, Currency, CryptoAddress, BankAccount,
    KYC, LoginSession, Notification, ExchangeRate, Role, MoneyRequest,
    ScheduledPayment, GroupPayment, GroupPaymentParticipant, SavingsGoal,
    PriceAlert, PaymentLink,
)
from . import db as rawsql

User = get_user_model()


# =====================================================
# BREACHED-PASSWORD CHECK (HaveIBeenPwned, k-anonymity API)
#
# Only the first 5 hex chars of the SHA1 hash are ever sent over the
# network — HIBP's k-anonymity model means the real password (and
# even its full hash) never leaves this server. If the API can't be
# reached (offline dev, this sandbox's own network allow-list, HIBP
# downtime, etc.) this FAILS OPEN — registration is allowed rather
# than blocked by a third-party outage. That's a deliberate
# availability-over-strictness tradeoff; flip it to fail-closed if
# your threat model prefers that instead.
# =====================================================

def _password_is_known_breached(raw_password):

    import hashlib
    import requests

    sha1 = hashlib.sha1(raw_password.encode('utf-8')).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]

    try:
        resp = requests.get(
            f"https://api.pwnedpasswords.com/range/{prefix}", timeout=3,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return False  # fail open — see note above

    for line in resp.text.splitlines():
        line_suffix, _, _count = line.partition(':')
        if line_suffix == suffix:
            return True

    return False


# =====================================================
# USER / AUTH
# =====================================================

class RegisterSerializer(serializers.ModelSerializer):

    password = serializers.CharField(
        write_only=True, validators=[validate_password]
    )
    confirmPassword = serializers.CharField(write_only=True)
    preferred_currency = serializers.CharField(
        write_only=True, required=False, default='BDT'
    )
    referral_code = serializers.CharField(
        write_only=True, required=False, allow_blank=True, default=''
    )

    class Meta:
        model = User
        fields = [
            'id', 'name', 'email', 'phone',
            'password', 'confirmPassword', 'preferred_currency',
            'referral_code',
        ]
        read_only_fields = ['id']

    def validate_password(self, value):

        if _password_is_known_breached(value):
            raise serializers.ValidationError(
                "This password has appeared in known data breaches. "
                "Please choose a different one."
            )

        return value

    def validate_referral_code(self, value):

        value = (value or '').strip().upper()
        if value and not rawsql.exists_where(
            User, "referral_code = %s", [value]
        ):
            raise serializers.ValidationError("That referral code doesn't exist.")
        return value

    def validate_email(self, value):

        if rawsql.exists_where(User, "LOWER(email) = LOWER(%s)", [value]):
            raise serializers.ValidationError(
                "An account with this email already exists."
            )

        return value

    def validate_phone(self, value):

        if rawsql.exists_where(User, "phone = %s", [value]):
            raise serializers.ValidationError(
                "An account with this phone number already exists."
            )

        return value

    def validate_preferred_currency(self, value):

        if not rawsql.exists_where(Currency, "currency_name = %s", [value]):
            raise serializers.ValidationError(
                "Unknown currency. Choose from the supported currency list."
            )

        return value

    def validate(self, data):

        if data['password'] != data['confirmPassword']:
            raise serializers.ValidationError(
                {"confirmPassword": "Passwords do not match."}
            )

        return data

    def create(self, validated_data):
        """
        Raw-SQL equivalent of `User.objects.create_user(...)` — inserts
        the row directly instead of going through the manager, then
        hydrates a User instance from the freshly-inserted row (never
        touching `.objects` / `.save()`).
        """
        from django.contrib.auth.hashers import make_password
        from django.utils import timezone
        from .models import generate_referral_code

        validated_data.pop('confirmPassword')
        validated_data.pop('preferred_currency', None)
        referral_code = (validated_data.pop('referral_code', '') or '').strip().upper()

        referrer_id = None
        if referral_code:
            referrer_row = rawsql.find_one(
                User, "referral_code = %s", [referral_code]
            )
            if referrer_row:
                referrer_id = referrer_row['id']

        now = timezone.now()
        new_id = rawsql.insert(
            User,
            password=make_password(validated_data['password']),
            last_login=None,
            is_superuser=False,
            first_name='',
            last_name='',
            is_staff=False,
            is_active=True,
            date_joined=now,
            email=User.objects.normalize_email(validated_data['email']),
            name=validated_data['name'],
            phone=validated_data['phone'],
            status='ACTIVE',
            registration_date=now,
            transaction_pin_hash=None,
            flagged_at=None,
            flagged_reason='',
            is_flagged=False,
            recovery_codes_hash='[]',
            referral_code=generate_referral_code(),
            referred_by_id=referrer_id,
            two_factor_enabled=False,
            two_factor_secret=None,
            account_type='PERSONAL',
            business_name='',
        )

        row = rawsql.get_row(User, 'id', new_id)
        return rawsql.hydrate(User, row)


class UserSerializer(serializers.ModelSerializer):

    roles = serializers.SerializerMethodField()
    kyc_tier = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'name', 'email', 'phone', 'status',
            'registration_date', 'roles', 'two_factor_enabled',
            'is_flagged', 'referral_code', 'kyc_tier', 'is_staff',
            'account_type', 'business_name',
        ]
        read_only_fields = [
            'id', 'email', 'phone', 'status', 'registration_date',
            'two_factor_enabled', 'is_flagged', 'referral_code',
            'kyc_tier', 'is_staff',
        ]

    def get_roles(self, obj):
        rows = rawsql.fetchall(
            "SELECT r.role_name FROM wallet_userrole ur "
            "JOIN wallet_role r ON r.id = ur.role_id WHERE ur.user_id = %s",
            [obj.id],
        )
        return [row['role_name'] for row in rows]

    def get_kyc_tier(self, obj):
        return obj.kyc_tier()


class ChangePasswordSerializer(serializers.Serializer):

    currentPassword = serializers.CharField(write_only=True)
    newPassword = serializers.CharField(
        write_only=True, validators=[validate_password]
    )


# =====================================================
# FORGOT / RESET PASSWORD
# =====================================================

class PasswordResetRequestSerializer(serializers.Serializer):

    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):

    uid = serializers.CharField()
    token = serializers.CharField()
    newPassword = serializers.CharField(
        write_only=True, validators=[validate_password]
    )


# =====================================================
# TRANSACTION PIN
# =====================================================

class SetTransactionPinSerializer(serializers.Serializer):

    currentPassword = serializers.CharField(write_only=True)
    pin = serializers.RegexField(
        regex=r'^\d{4,6}$',
        error_messages={'invalid': 'PIN must be 4-6 digits.'},
        write_only=True,
    )


# =====================================================
# CURRENCY
# =====================================================

class CurrencySerializer(serializers.ModelSerializer):

    class Meta:
        model = Currency
        fields = ['currency_name', 'type', 'symbol']


# =====================================================
# BANK ACCOUNT
# =====================================================

class BankAccountSerializer(serializers.ModelSerializer):

    class Meta:
        model = BankAccount
        fields = ['id', 'bank_name', 'account_number', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_account_number(self, value):

        if not value.strip():
            raise serializers.ValidationError("Account number is required.")

        return value


# =====================================================
# CRYPTO ADDRESS
# =====================================================

class CryptoAddressSerializer(serializers.ModelSerializer):

    class Meta:
        model = CryptoAddress
        fields = ['address_id', 'blockchain', 'public_address']


# =====================================================
# WALLET
# =====================================================

class WalletSerializer(serializers.ModelSerializer):

    currency_type = serializers.CharField(source='currency.type', read_only=True)
    crypto_addresses = CryptoAddressSerializer(many=True, read_only=True)

    class Meta:
        model = Wallet
        fields = [
            'wallet_id', 'name', 'currency', 'currency_type', 'balance',
            'wallet_status', 'is_default_receive', 'created_at',
            'crypto_addresses',
        ]
        read_only_fields = [
            'wallet_id', 'balance', 'wallet_status',
            'is_default_receive', 'created_at',
        ]

    def validate_currency(self, value):

        if not rawsql.exists_where(
            Currency, "currency_name = %s", [value.currency_name]
        ):
            raise serializers.ValidationError("Unknown currency.")

        return value


class FundWalletSerializer(serializers.Serializer):

    amount = serializers.DecimalField(max_digits=24, decimal_places=8)

    def validate_amount(self, value):

        if value <= 0:
            raise serializers.ValidationError(
                "Amount must be greater than zero."
            )

        return value


# =====================================================
# TRANSACTION
#
# Read shape mirrors the original API (wallet_id/wallet_name/
# counterparty_*) so the existing transactions.js keeps working,
# but it's now derived per-request-user from a single row shared
# by both sides of the transfer.
# =====================================================

class TransactionSerializer(serializers.ModelSerializer):

    type = serializers.SerializerMethodField()
    wallet_id = serializers.SerializerMethodField()
    wallet_name = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    counterparty_wallet_id = serializers.SerializerMethodField()
    counterparty_wallet_name = serializers.SerializerMethodField()
    counterparty_amount = serializers.SerializerMethodField()
    counterparty_currency = serializers.SerializerMethodField()
    counterparty_phone = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source='date', read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'transaction_id', 'type', 'wallet_id', 'wallet_name',
            'currency', 'amount', 'counterparty_wallet_id',
            'counterparty_wallet_name', 'counterparty_amount',
            'counterparty_currency', 'counterparty_phone',
            'exchange_rate', 'fee', 'status', 'category', 'created_at',
        ]

    def _is_sender_side(self, obj):

        user = self.context['request'].user
        return bool(obj.sender_wallet_id and obj.sender_wallet.user_id == user.id)

    def get_type(self, obj):

        if obj.transaction_type in ('SHIFT', 'EXCHANGE', 'DEPOSIT'):
            return obj.transaction_type

        return 'SEND' if self._is_sender_side(obj) else 'RECEIVE'

    def get_wallet_id(self, obj):

        wallet = obj.sender_wallet if self._is_sender_side(obj) else obj.receiver_wallet
        return wallet.wallet_id if wallet else None

    def get_wallet_name(self, obj):

        wallet = obj.sender_wallet if self._is_sender_side(obj) else obj.receiver_wallet
        return wallet.name if wallet else None

    def get_currency(self, obj):

        wallet = obj.sender_wallet if self._is_sender_side(obj) else obj.receiver_wallet
        return wallet.currency_id if wallet else None

    def get_counterparty_wallet_id(self, obj):

        wallet = obj.receiver_wallet if self._is_sender_side(obj) else obj.sender_wallet
        return wallet.wallet_id if wallet else None

    def get_counterparty_wallet_name(self, obj):

        wallet = obj.receiver_wallet if self._is_sender_side(obj) else obj.sender_wallet
        return wallet.name if wallet else None

    def get_counterparty_amount(self, obj):

        if self._is_sender_side(obj):
            return str(obj.received_amount) if obj.received_amount is not None else str(obj.amount)

        return str(obj.amount)

    def get_counterparty_currency(self, obj):

        wallet = obj.receiver_wallet if self._is_sender_side(obj) else obj.sender_wallet
        return wallet.currency_id if wallet else None

    def get_counterparty_phone(self, obj):

        wallet = obj.receiver_wallet if self._is_sender_side(obj) else obj.sender_wallet
        return wallet.user.phone if wallet else None


class SendSerializer(serializers.Serializer):
    """
    bKash-style send. Always requires the sender's own wallet.
    Exactly one of recipient_phone / recipient_wallet_id must be
    given:

      - recipient_phone: external transfer to another account's
        number. Funds always land in *their* default receive
        wallet (converted if currencies differ).

      - recipient_wallet_id: internal shift between two of the
        *sender's own* wallets (converted if currencies differ).
    """

    sender_wallet_id = serializers.CharField()
    recipient_phone = serializers.CharField(required=False, allow_blank=True)
    recipient_wallet_id = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=24, decimal_places=8)
    # Only required if the user has already set a transaction PIN
    # (see check_transaction_pin() in views.py). Optional so existing
    # accounts without a PIN keep working unchanged.
    pin = serializers.CharField(required=False, allow_blank=True, write_only=True)
    # Personal budgeting tag, purely descriptive (e.g. "Food", "Bills").
    category = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_amount(self, value):

        if value <= 0:
            raise serializers.ValidationError(
                "Amount must be greater than zero."
            )

        return value

    def validate(self, data):

        phone = data.get('recipient_phone', '').strip()
        wallet_id = data.get('recipient_wallet_id', '').strip()

        if bool(phone) == bool(wallet_id):
            raise serializers.ValidationError(
                "Provide either recipient_phone (send to an account) "
                "or recipient_wallet_id (shift to your own wallet) — not both."
            )

        data['recipient_phone'] = phone
        data['recipient_wallet_id'] = wallet_id

        return data


class ExchangeSerializer(serializers.Serializer):

    from_wallet_id = serializers.CharField()
    to_wallet_id = serializers.CharField()
    amount = serializers.DecimalField(max_digits=24, decimal_places=8)
    pin = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate_amount(self, value):

        if value <= 0:
            raise serializers.ValidationError(
                "Amount must be greater than zero."
            )

        return value


# =====================================================
# KYC / SESSIONS / NOTIFICATIONS / RATES / ROLES
# =====================================================

class KYCSerializer(serializers.ModelSerializer):

    class Meta:
        model = KYC
        fields = [
            'id', 'nid_number', 'passport_number',
            'verification_status', 'submission_date',
            'admin_remarks', 'reviewed_at',
        ]
        read_only_fields = [
            'id', 'verification_status', 'submission_date',
            'admin_remarks', 'reviewed_at',
        ]

    def validate(self, data):

        if not data.get('nid_number') and not data.get('passport_number'):
            raise serializers.ValidationError(
                "Provide at least an NID number or a passport number."
            )

        return data


# =====================================================
# ADMIN — KYC REVIEW
# =====================================================

class AdminKYCSerializer(serializers.ModelSerializer):
    """Read shape for the admin KYC queue — includes who it belongs to."""

    user_name = serializers.CharField(source='user.name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)

    class Meta:
        model = KYC
        fields = [
            'id', 'user_name', 'user_email', 'user_phone',
            'nid_number', 'passport_number', 'verification_status',
            'submission_date', 'admin_remarks', 'reviewed_at',
        ]


class AdminKYCActionSerializer(serializers.Serializer):

    remarks = serializers.CharField(
        required=False, allow_blank=True, max_length=255
    )


class LoginSessionSerializer(serializers.ModelSerializer):

    class Meta:
        model = LoginSession
        fields = ['id', 'ip_address', 'device_info', 'login_time']


class NotificationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Notification
        fields = ['id', 'message', 'type', 'read_status', 'timestamp']
        read_only_fields = ['id', 'message', 'type', 'timestamp']


class ExchangeRateSerializer(serializers.ModelSerializer):

    class Meta:
        model = ExchangeRate
        fields = ['rate_id', 'from_curr', 'to_curr', 'rate', 'last_updated']


class RoleSerializer(serializers.ModelSerializer):

    class Meta:
        model = Role
        fields = ['id', 'role_name']


# =====================================================
# MONEY REQUEST  (the reverse of Send)
# =====================================================

class MoneyRequestSerializer(serializers.ModelSerializer):
    """Read shape, direction-aware like TransactionSerializer."""

    direction = serializers.SerializerMethodField()
    requester_name = serializers.CharField(source='requester.name', read_only=True)
    requester_phone = serializers.CharField(source='requester.phone', read_only=True)
    payer_name = serializers.CharField(source='payer.name', read_only=True)
    payer_phone = serializers.CharField(source='payer.phone', read_only=True)
    currency = serializers.CharField(source='requester_wallet.currency_id', read_only=True)

    class Meta:
        model = MoneyRequest
        fields = [
            'request_id', 'direction', 'amount', 'currency', 'note', 'status',
            'requester_name', 'requester_phone', 'payer_name', 'payer_phone',
            'created_at', 'responded_at',
        ]

    def get_direction(self, obj):
        user = self.context['request'].user
        return 'OUTGOING' if obj.requester_id == user.id else 'INCOMING'


class MoneyRequestCreateSerializer(serializers.Serializer):
    """
    Create a request addressed to another account's phone number, for
    an amount that will land in one of the requester's own wallets
    (defaults to their default-receive wallet if not given).
    """

    payer_phone = serializers.CharField()
    amount = serializers.DecimalField(max_digits=24, decimal_places=8)
    requester_wallet_id = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_amount(self, value):

        if value <= 0:
            raise serializers.ValidationError(
                "Amount must be greater than zero."
            )

        return value


class MoneyRequestRespondSerializer(serializers.Serializer):
    """Used by the payer to accept a request: which of their own
    wallets to pay from, and their PIN if they've set one."""

    payer_wallet_id = serializers.CharField()
    pin = serializers.CharField(required=False, allow_blank=True, write_only=True)


# =====================================================
# TWO-FACTOR AUTHENTICATION (TOTP)
# =====================================================

class TwoFactorConfirmSerializer(serializers.Serializer):
    """Used both to confirm initial setup and to verify a 2FA
    challenge at login time."""
    code = serializers.CharField(max_length=8)


class TwoFactorLoginVerifySerializer(serializers.Serializer):
    """
    Step 2 of a 2FA-protected login: the client got a `login_token`
    back from LoginView instead of access/refresh tokens, and now
    submits it alongside the 6-digit app code (or an unused recovery
    code) to actually receive access/refresh tokens.
    """
    login_token = serializers.CharField()
    code = serializers.CharField(max_length=10)


# =====================================================
# SCHEDULED / RECURRING PAYMENTS
# =====================================================

class ScheduledPaymentSerializer(serializers.ModelSerializer):

    recipient_phone = serializers.CharField(required=False, allow_null=True)
    recipient_wallet_id = serializers.CharField(
        required=False, allow_null=True, read_only=True,
    )

    class Meta:
        model = ScheduledPayment
        fields = [
            'schedule_id', 'sender_wallet', 'recipient_phone',
            'recipient_wallet_id', 'amount', 'note', 'frequency',
            'next_run_at', 'last_run_at', 'status', 'created_at',
        ]
        read_only_fields = ['schedule_id', 'last_run_at', 'created_at']


class ScheduledPaymentCreateSerializer(serializers.Serializer):

    sender_wallet_id = serializers.CharField()
    recipient_phone = serializers.CharField(required=False, allow_blank=True)
    recipient_wallet_id = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=24, decimal_places=8)
    note = serializers.CharField(required=False, allow_blank=True, default='')
    frequency = serializers.ChoiceField(
        choices=['ONCE', 'DAILY', 'WEEKLY', 'MONTHLY']
    )
    next_run_at = serializers.DateTimeField()

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate(self, data):
        if not data.get('recipient_phone') and not data.get('recipient_wallet_id'):
            raise serializers.ValidationError(
                "Provide either recipient_phone or recipient_wallet_id."
            )
        return data


# =====================================================
# ACCOUNT TYPE / DEACTIVATION
# =====================================================

class AccountTypeUpdateSerializer(serializers.Serializer):

    account_type = serializers.ChoiceField(choices=['PERSONAL', 'MERCHANT'])
    business_name = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, data):
        if data['account_type'] == 'MERCHANT' and not data.get('business_name'):
            raise serializers.ValidationError(
                {"business_name": "Required when switching to a Merchant account."}
            )
        return data


class DeactivateAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)


# =====================================================
# GROUP PAYMENT (SPLIT BILL)
# =====================================================

class GroupPaymentParticipantSerializer(serializers.ModelSerializer):

    user_name = serializers.CharField(source='user.name', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)

    class Meta:
        model = GroupPaymentParticipant
        fields = ['id', 'user_name', 'user_phone', 'share_amount', 'status', 'paid_at']


class GroupPaymentSerializer(serializers.ModelSerializer):

    # NOT sourced from the real `participants` reverse-FK relation:
    # that field is a data descriptor that forbids direct attribute
    # assignment ("Direct assignment to the reverse side of a related
    # set is prohibited"), so callers attach the raw-SQL-fetched list
    # to `._participants` instead (see get_group_payment_or_404() in
    # views.py) and this method field reads it from there.
    participants = serializers.SerializerMethodField()
    organizer_name = serializers.CharField(source='organizer.name', read_only=True)

    class Meta:
        model = GroupPayment
        fields = [
            'group_payment_id', 'organizer_name', 'receiver_wallet',
            'title', 'total_amount', 'status', 'participants', 'created_at',
        ]

    def get_participants(self, obj):
        return GroupPaymentParticipantSerializer(
            getattr(obj, '_participants', []), many=True
        ).data


class GroupPaymentCreateSerializer(serializers.Serializer):

    receiver_wallet_id = serializers.CharField()
    title = serializers.CharField(max_length=100)
    total_amount = serializers.DecimalField(max_digits=24, decimal_places=8)
    # List of {"phone": "...", "share_amount": "..."}. Shares don't
    # have to sum exactly to total_amount (e.g. the organizer might
    # cover a rounding gap themselves) — that's intentionally not
    # enforced, just informational.
    participants = serializers.ListField(child=serializers.DictField())

    def validate_total_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_participants(self, value):
        if not value:
            raise serializers.ValidationError("Add at least one participant.")
        for p in value:
            if 'phone' not in p or 'share_amount' not in p:
                raise serializers.ValidationError(
                    "Each participant needs 'phone' and 'share_amount'."
                )
        return value


# =====================================================
# SAVINGS GOALS
# =====================================================

class SavingsGoalSerializer(serializers.ModelSerializer):

    progress_percent = serializers.SerializerMethodField()
    current_amount = serializers.SerializerMethodField()

    class Meta:
        model = SavingsGoal
        fields = [
            'goal_id', 'savings_wallet', 'name', 'target_amount', 'deadline',
            'auto_save_percent', 'is_active', 'progress_percent',
            'current_amount', 'created_at',
        ]

    def get_progress_percent(self, obj):
        return obj.progress_percent()

    def get_current_amount(self, obj):
        return obj.savings_wallet.balance


class SavingsGoalCreateSerializer(serializers.Serializer):

    savings_wallet_id = serializers.CharField()
    name = serializers.CharField(max_length=100)
    target_amount = serializers.DecimalField(max_digits=24, decimal_places=8)
    deadline = serializers.DateField(required=False, allow_null=True)
    auto_save_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0
    )

    def validate_target_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Target must be greater than zero.")
        return value

    def validate_auto_save_percent(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Must be between 0 and 100.")
        return value


class SavingsGoalTopUpSerializer(serializers.Serializer):

    from_wallet_id = serializers.CharField()
    amount = serializers.DecimalField(max_digits=24, decimal_places=8)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value


# =====================================================
# PRICE ALERTS
# =====================================================

class PriceAlertSerializer(serializers.ModelSerializer):

    class Meta:
        model = PriceAlert
        fields = [
            'alert_id', 'from_currency', 'to_currency', 'threshold_rate',
            'is_active', 'triggered_at', 'created_at',
        ]
        read_only_fields = ['alert_id', 'triggered_at', 'created_at']

    def validate_threshold_rate(self, value):
        if value <= 0:
            raise serializers.ValidationError("Must be greater than zero.")
        return value


# =====================================================
# MERCHANT PAYMENT LINKS
# =====================================================

class PaymentLinkSerializer(serializers.ModelSerializer):

    class Meta:
        model = PaymentLink
        fields = [
            'link_id', 'receiving_wallet', 'title', 'amount',
            'is_active', 'created_at',
        ]
        read_only_fields = ['link_id', 'created_at']


class PaymentLinkPaySerializer(serializers.Serializer):
    """Used by a payer (any logged-in user) hitting a merchant's
    public payment link."""

    payer_wallet_id = serializers.CharField()
    # Only required when the link itself doesn't fix an amount.
    amount = serializers.DecimalField(
        max_digits=24, decimal_places=8, required=False
    )

    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value


# =====================================================
# BANK ACCOUNT DEPOSIT / WITHDRAW
# =====================================================

class BankDepositSerializer(serializers.Serializer):
    wallet_id = serializers.CharField()
    amount = serializers.DecimalField(max_digits=24, decimal_places=8, min_value=Decimal("0.00000001"))


class BankWithdrawSerializer(serializers.Serializer):
    wallet_id = serializers.CharField()
    amount = serializers.DecimalField(max_digits=24, decimal_places=8, min_value=Decimal("0.00000001"))
