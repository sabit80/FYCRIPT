import secrets
import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models


def generate_referral_code():
    return secrets.token_hex(4).upper()


# =====================================================
# USER  (ERD: USER)
#
# The account is identified by phone number (bKash-style) as
# well as email/login. One person == one account == one phone
# number. The frontend's create-account.js/login.js work with
# {id, name, email, phone, password}; a custom User model keeps
# that shape while Django still hashes the password for us.
# =====================================================

phone_validator = RegexValidator(
    regex=r'^\+?[0-9]{9,15}$',
    message="Enter a valid phone number (9-15 digits, optional leading +).",
)


class UserManager(BaseUserManager):

    def create_user(self, email, name, phone, password=None, **extra_fields):

        if not email:
            raise ValueError("Users must have an email address")
        if not phone:
            raise ValueError("Users must have a phone number")

        email = self.normalize_email(email)
        user = self.model(email=email, name=name, phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, phone, password=None, **extra_fields):

        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, name, phone, password, **extra_fields)


USER_STATUS_CHOICES = [
    ('ACTIVE', 'Active'),
    ('SUSPENDED', 'Suspended'),
    ('CLOSED', 'Closed'),
]


class User(AbstractUser):

    username = None
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150)

    # Account identifier for peer-to-peer transfers, exactly like a
    # bKash/mobile-money number. One user -> one account -> one phone.
    phone = models.CharField(
        max_length=20, unique=True, validators=[phone_validator]
    )

    status = models.CharField(
        max_length=10, choices=USER_STATUS_CHOICES, default='ACTIVE'
    )
    registration_date = models.DateTimeField(auto_now_add=True)

    # Optional extra PIN required before Send/Exchange (separate from the
    # login password). Stored hashed with Django's own password hasher —
    # never in plaintext. Null until the user sets one via
    # SetTransactionPinView.
    transaction_pin_hash = models.CharField(max_length=128, blank=True, null=True)

    # ---- Two-Factor Authentication (TOTP, e.g. Google/Microsoft
    # Authenticator). two_factor_secret is only ever populated once the
    # user has *confirmed* a code against it (see Enable2FAConfirmView) —
    # a secret generated but never confirmed is thrown away on the next
    # setup attempt. recovery_codes_hash stores one-time backup codes as
    # a JSON list of Django password hashes (never plaintext).
    two_factor_enabled = models.BooleanField(default=False)
    two_factor_secret = models.CharField(max_length=64, blank=True, null=True)
    recovery_codes_hash = models.JSONField(blank=True, default=list)

    # ---- Fraud / risk flag. Set automatically by the velocity check in
    # views.py (too many sends too fast) or manually by an admin. A
    # flagged account can still log in and view its data but SendView /
    # ExchangeView refuse new outgoing transfers until an admin clears it.
    is_flagged = models.BooleanField(default=False)
    flagged_reason = models.CharField(max_length=255, blank=True, default='')
    flagged_at = models.DateTimeField(blank=True, null=True)

    # ---- Referrals. Every user gets a unique code at creation; signing
    # up with someone else's code links the two accounts (see
    # RegisterView) so a bonus can be credited to both.
    referral_code = models.CharField(
        max_length=12, unique=True, default=generate_referral_code, editable=False,
    )
    referred_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='referrals',
    )

    # ---- Merchant / personal account type. MERCHANT unlocks the
    # PaymentLink feature (see PaymentLink model below); it doesn't
    # change any wallet/send logic on its own.
    ACCOUNT_TYPE_CHOICES = [
        ('PERSONAL', 'Personal'),
        ('MERCHANT', 'Merchant'),
    ]
    account_type = models.CharField(
        max_length=10, choices=ACCOUNT_TYPE_CHOICES, default='PERSONAL'
    )
    business_name = models.CharField(max_length=100, blank=True, default='')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name', 'phone']

    objects = UserManager()

    def __str__(self):
        return f"{self.name} ({self.phone})"

    def set_transaction_pin(self, raw_pin):
        from django.contrib.auth.hashers import make_password
        self.transaction_pin_hash = make_password(raw_pin)

    def check_transaction_pin(self, raw_pin):
        from django.contrib.auth.hashers import check_password
        if not self.transaction_pin_hash:
            return False
        return check_password(raw_pin, self.transaction_pin_hash)

    def kyc_tier(self):
        """
        Used by the daily/monthly send-limit check in views.py.
        No KYC row, or a PENDING/REJECTED one, keeps a user on the
        lowest ('UNVERIFIED') tier; only an APPROVED KYC row unlocks
        the higher limits.
        """
        from . import db as rawsql
        kyc_row = rawsql.get_kyc_by_user(self.id)
        if kyc_row and kyc_row['verification_status'] == 'APPROVED':
            return 'VERIFIED'
        return 'UNVERIFIED'


# =====================================================
# ROLE / USER_ROLE  (ERD: ROLE, USER_ROLE)
# =====================================================

class Role(models.Model):

    role_name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.role_name


class UserRole(models.Model):

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='user_roles'
    )
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name='user_roles'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'role')

    def __str__(self):
        return f"{self.user.phone} -> {self.role.role_name}"


# =====================================================
# KYC  (ERD: KYC)  -- zero-or-one per user (1/0 in the diagram)
# =====================================================

KYC_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('APPROVED', 'Approved'),
    ('REJECTED', 'Rejected'),
]


class KYC(models.Model):

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='kyc'
    )
    nid_number = models.CharField(max_length=50, blank=True, null=True)
    passport_number = models.CharField(max_length=50, blank=True, null=True)
    submission_date = models.DateTimeField(auto_now_add=True)
    verification_status = models.CharField(
        max_length=10, choices=KYC_STATUS_CHOICES, default='PENDING'
    )

    # Set when an admin approves/rejects (AdminKYCApproveView /
    # AdminKYCRejectView in views.py). Both stay null while PENDING.
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kyc_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_remarks = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"KYC({self.verification_status}) - {self.user.phone}"


# =====================================================
# BANK_ACCOUNT  (ERD: BANK_ACCOUNT)
# One account can connect one or many bank accounts.
# =====================================================

class BankAccount(models.Model):

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='bank_accounts'
    )
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'account_number')

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"


# =====================================================
# CURRENCY  (ERD: CURRENCY)
# =====================================================

CURRENCY_TYPE_CHOICES = [
    ('FIAT', 'Fiat'),
    ('CRYPTO', 'Crypto'),
]


class Currency(models.Model):

    currency_name = models.CharField(max_length=10, primary_key=True)
    type = models.CharField(max_length=10, choices=CURRENCY_TYPE_CHOICES)
    symbol = models.CharField(max_length=5, blank=True, default='')

    def __str__(self):
        return self.currency_name


# =====================================================
# WALLET  (ERD: WALLET)  -- USER "Owns" WALLET (1..*)
#
# Every user gets exactly one default receive wallet created at
# signup (the bKash-style "send to my number" target). Beyond
# that a user may open as many additional fiat/crypto wallets as
# they like.
# =====================================================

WALLET_STATUS_CHOICES = [
    ('ACTIVE', 'Active'),
    ('FROZEN', 'Frozen'),
    ('CLOSED', 'Closed'),
]


class Wallet(models.Model):

    wallet_id = models.CharField(max_length=40, primary_key=True, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='wallets'
    )
    currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, related_name='wallets'
    )
    name = models.CharField(max_length=100, blank=True)
    balance = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    wallet_status = models.CharField(
        max_length=10, choices=WALLET_STATUS_CHOICES, default='ACTIVE'
    )

    # True for exactly one wallet per user: the wallet that
    # receives money sent to this account's phone number.
    is_default_receive = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default_receive', 'currency_id']
        # NOTE: the original PostgreSQL build enforced "exactly one default
        # receive wallet per user" with a conditional (partial) unique
        # constraint. MySQL has no equivalent (unique indexes can't carry a
        # WHERE condition), so that rule is enforced in save() below instead.

    def save(self, *args, **kwargs):
        # NOTE: this override only fills in defaults for a not-yet-saved
        # instance and, historically, unset any other default-receive
        # wallet via the ORM. All actual reads/writes of Wallet rows now
        # go through wallet/db.py (see WalletListCreateView etc in
        # views.py) instead of calling this method — kept here only so
        # nothing else that still constructs a bare `Wallet(...)` and
        # calls `.save()` breaks; the ORM `.filter().update()` call that
        # used to live here has been removed (see db.unset_other_default_wallets).

        if not self.wallet_id:
            self.wallet_id = f"WAL-{uuid.uuid4().hex[:10].upper()}"

        if not self.name:
            self.name = f"{self.currency_id} Wallet"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.currency_id}) - {self.user.phone}"


# =====================================================
# CRYPTO_ADDRESS  (ERD: CRYPTO_ADDRESS)  -- WALLET "has" CRYPTO_ADDRESS
# =====================================================

class CryptoAddress(models.Model):

    address_id = models.CharField(max_length=40, primary_key=True, editable=False)
    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name='crypto_addresses'
    )
    blockchain = models.CharField(max_length=50)
    public_address = models.CharField(max_length=120, unique=True, editable=False)

    def save(self, *args, **kwargs):

        if not self.address_id:
            self.address_id = f"ADR-{uuid.uuid4().hex[:10].upper()}"

        if not self.public_address:
            self.public_address = uuid.uuid4().hex

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.blockchain}:{self.public_address}"


# =====================================================
# EXCHANGE_RATE  (ERD: EXCHANGE_RATE)  -- CURRENCY "converts" CURRENCY
# =====================================================

class ExchangeRate(models.Model):

    rate_id = models.AutoField(primary_key=True)
    from_curr = models.ForeignKey(
        Currency, on_delete=models.CASCADE, related_name='rates_from'
    )
    to_curr = models.ForeignKey(
        Currency, on_delete=models.CASCADE, related_name='rates_to'
    )
    rate = models.DecimalField(max_digits=24, decimal_places=8)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('from_curr', 'to_curr')

    def __str__(self):
        return f"1 {self.from_curr_id} = {self.rate} {self.to_curr_id}"


# =====================================================
# TRANSACTION  (ERD: TRANSACTION)  -- WALLET "Performs" TRANSACTION
#
# One row per real-world transfer (not duplicated per user). The
# API serializer derives a per-user "direction" (SEND/RECEIVE/...)
# by comparing sender_wallet.user / receiver_wallet.user against
# the requesting user.
# =====================================================

TRANSACTION_TYPE_CHOICES = [
    ('SEND', 'Send'),          # wallet -> another account's phone
    ('RECEIVE', 'Receive'),    # incoming from another account
    ('SHIFT', 'Shift'),        # wallet -> own wallet (internal move)
    ('EXCHANGE', 'Exchange'),  # currency conversion between own wallets
    ('DEPOSIT', 'Deposit'),    # top-up / fund a wallet (incl. from a bank account)
    ('WITHDRAW', 'Withdraw'),  # wallet -> linked bank account
]

TRANSACTION_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('COMPLETED', 'Completed'),
    ('FAILED', 'Failed'),
]


class Transaction(models.Model):

    transaction_id = models.CharField(max_length=40, primary_key=True, editable=False)

    sender_wallet = models.ForeignKey(
        Wallet, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sent_transactions',
    )
    receiver_wallet = models.ForeignKey(
        Wallet, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='received_transactions',
    )

    transaction_type = models.CharField(
        max_length=10, choices=TRANSACTION_TYPE_CHOICES
    )
    amount = models.DecimalField(max_digits=24, decimal_places=8)
    received_amount = models.DecimalField(
        max_digits=24, decimal_places=8, blank=True, null=True
    )
    fee = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    exchange_rate = models.DecimalField(
        max_digits=24, decimal_places=8, blank=True, null=True
    )
    status = models.CharField(
        max_length=10, choices=TRANSACTION_STATUS_CHOICES, default='COMPLETED'
    )
    # Free-text personal budgeting tag (e.g. "Food", "Bills", "Shopping").
    # Purely descriptive — never used in any balance/fee/limit logic.
    category = models.CharField(max_length=40, blank=True, default='')
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def save(self, *args, **kwargs):

        if not self.transaction_id:
            self.transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.transaction_type} {self.amount} ({self.transaction_id})"


# =====================================================
# NOTIFICATION  (ERD: NOTIFICATION)
# =====================================================

NOTIFICATION_TYPES = [
    ('INFO', 'Info'),
    ('TRANSACTION', 'Transaction'),
    ('SECURITY', 'Security'),
]


class Notification(models.Model):

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='notifications'
    )
    message = models.CharField(max_length=255)
    type = models.CharField(
        max_length=15, choices=NOTIFICATION_TYPES, default='INFO'
    )
    read_status = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Notification({self.type}) - {self.user.phone}"


# =====================================================
# AUDIT_LOG  (ERD: AUDIT_LOG)
# =====================================================

class AuditLog(models.Model):

    log_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name='audit_logs',
        blank=True, null=True,
    )
    action = models.CharField(max_length=100)
    remarks = models.CharField(max_length=255, blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        user_label = self.user.phone if self.user else 'system'
        return f"AuditLog({self.action}) - {user_label}"


# =====================================================
# LOGIN SESSION
# (not in the ERD proper, kept from the original build —
#  used for the Settings -> Active Sessions panel)
# =====================================================

class LoginSession(models.Model):

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='login_sessions'
    )
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    device_info = models.CharField(max_length=255, blank=True, null=True)
    login_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-login_time']

    def __str__(self):
        return f"Session({self.user.phone}) @ {self.login_time}"


# =====================================================
# MONEY_REQUEST
#
# The reverse of Send: user A asks user B for money. B can accept
# (which performs a normal transfer from one of B's wallets into
# A's default receive wallet) or decline. Not in the original ERD —
# added as its own table since it has its own lifecycle
# (PENDING/ACCEPTED/DECLINED) separate from an actual transaction.
# =====================================================

MONEY_REQUEST_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('ACCEPTED', 'Accepted'),
    ('DECLINED', 'Declined'),
]


class MoneyRequest(models.Model):

    request_id = models.CharField(max_length=40, primary_key=True, editable=False)

    requester = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='money_requests_made'
    )
    # The wallet that will receive the funds if accepted (must belong
    # to the requester; defaults to their default-receive wallet).
    requester_wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name='money_requests_in'
    )

    payer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='money_requests_received'
    )

    amount = models.DecimalField(max_digits=24, decimal_places=8)
    note = models.CharField(max_length=255, blank=True, default='')

    status = models.CharField(
        max_length=10, choices=MONEY_REQUEST_STATUS_CHOICES, default='PENDING'
    )
    # Filled in only if accepted, linking to the resulting transfer.
    transaction = models.ForeignKey(
        Transaction, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fulfilled_request',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):

        if not self.request_id:
            self.request_id = f"REQ-{uuid.uuid4().hex[:12].upper()}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"MoneyRequest({self.status}) {self.requester.phone} <- {self.payer.phone}"


# =====================================================
# SCHEDULED_PAYMENT
#
# Recurring / future-dated transfers. Not in the original ERD —
# added as its own table since it has a lifecycle (ACTIVE/PAUSED/
# CANCELLED) independent of the Transaction rows it eventually
# produces. Actually *executing* due payments is done by the
# `run_scheduled_payments` management command (wallet/management/
# commands/run_scheduled_payments.py) — wire that into cron or
# Celery beat to run e.g. every hour; it is idempotent per due date.
# =====================================================

SCHEDULE_FREQUENCY_CHOICES = [
    ('ONCE', 'One time (on next_run_at only)'),
    ('DAILY', 'Daily'),
    ('WEEKLY', 'Weekly'),
    ('MONTHLY', 'Monthly'),
]

SCHEDULE_STATUS_CHOICES = [
    ('ACTIVE', 'Active'),
    ('PAUSED', 'Paused'),
    ('CANCELLED', 'Cancelled'),
]


class ScheduledPayment(models.Model):

    schedule_id = models.CharField(max_length=40, primary_key=True, editable=False)

    owner = models.ForeignKey(
        'User', on_delete=models.CASCADE, related_name='scheduled_payments'
    )
    sender_wallet = models.ForeignKey(
        'Wallet', on_delete=models.CASCADE, related_name='scheduled_sends'
    )

    # Exactly one of these two is set, same SEND-vs-SHIFT split as
    # SendSerializer uses today.
    recipient_phone = models.CharField(max_length=20, blank=True, null=True)
    recipient_wallet = models.ForeignKey(
        'Wallet', on_delete=models.CASCADE, null=True, blank=True,
        related_name='scheduled_receives',
    )

    amount = models.DecimalField(max_digits=24, decimal_places=8)
    note = models.CharField(max_length=255, blank=True, default='')

    frequency = models.CharField(max_length=10, choices=SCHEDULE_FREQUENCY_CHOICES)
    next_run_at = models.DateTimeField()
    last_run_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=SCHEDULE_STATUS_CHOICES, default='ACTIVE'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['next_run_at']

    def save(self, *args, **kwargs):

        if not self.schedule_id:
            self.schedule_id = f"SCH-{uuid.uuid4().hex[:10].upper()}"

        super().save(*args, **kwargs)

    def advance(self):
        """Push next_run_at forward by one period; caller saves."""
        from datetime import timedelta

        if self.frequency == 'DAILY':
            self.next_run_at += timedelta(days=1)
        elif self.frequency == 'WEEKLY':
            self.next_run_at += timedelta(weeks=1)
        elif self.frequency == 'MONTHLY':
            self.next_run_at += timedelta(days=30)
        else:  # ONCE
            self.status = 'CANCELLED'

    def __str__(self):
        return f"ScheduledPayment({self.frequency}) {self.owner.phone} - {self.amount}"


# =====================================================
# GROUP PAYMENT (SPLIT BILL)
#
# One user (the organizer) creates a GroupPayment for a total amount,
# then adds one GroupPaymentParticipant row per person who owes a
# share. Each participant pays their own share independently (via
# GroupPaymentPayShareView, which reuses the same SEND logic/fees as
# everywhere else) — the organizer never fronts the whole amount.
# =====================================================

GROUP_PAYMENT_STATUS_CHOICES = [
    ('OPEN', 'Open'),
    ('COMPLETED', 'Completed'),
    ('CANCELLED', 'Cancelled'),
]

PARTICIPANT_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('PAID', 'Paid'),
]


class GroupPayment(models.Model):

    group_payment_id = models.CharField(max_length=40, primary_key=True, editable=False)

    organizer = models.ForeignKey(
        'User', on_delete=models.CASCADE, related_name='organized_group_payments'
    )
    receiver_wallet = models.ForeignKey(
        'Wallet', on_delete=models.CASCADE, related_name='group_payment_receipts',
        help_text="Wallet that collects everyone's share (usually the organizer's).",
    )

    title = models.CharField(max_length=100)
    total_amount = models.DecimalField(max_digits=24, decimal_places=8)
    status = models.CharField(
        max_length=10, choices=GROUP_PAYMENT_STATUS_CHOICES, default='OPEN'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.group_payment_id:
            self.group_payment_id = f"GRP-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def refresh_status(self):
        """Marks itself COMPLETED once every participant has paid.
        Called after each participant payment; caller saves."""
        from . import db as rawsql
        if not rawsql.group_payment_has_unpaid_participants(self.group_payment_id):
            self.status = 'COMPLETED'

    def __str__(self):
        return f"GroupPayment({self.title}) {self.total_amount}"


class GroupPaymentParticipant(models.Model):

    group_payment = models.ForeignKey(
        GroupPayment, on_delete=models.CASCADE, related_name='participants'
    )
    user = models.ForeignKey(
        'User', on_delete=models.CASCADE, related_name='group_payment_shares'
    )
    share_amount = models.DecimalField(max_digits=24, decimal_places=8)
    status = models.CharField(
        max_length=10, choices=PARTICIPANT_STATUS_CHOICES, default='PENDING'
    )
    transaction = models.ForeignKey(
        Transaction, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='group_payment_share',
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('group_payment', 'user')]

    def __str__(self):
        return f"{self.user.phone} owes {self.share_amount} ({self.status})"


# =====================================================
# SAVINGS GOAL / AUTO-SAVE
# =====================================================

class SavingsGoal(models.Model):

    goal_id = models.CharField(max_length=40, primary_key=True, editable=False)

    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='savings_goals')
    savings_wallet = models.ForeignKey(
        'Wallet', on_delete=models.CASCADE, related_name='savings_goals'
    )

    name = models.CharField(max_length=100)
    target_amount = models.DecimalField(max_digits=24, decimal_places=8)
    deadline = models.DateField(null=True, blank=True)

    # If set, every SEND from this user auto-transfers this percentage
    # of the sent amount into savings_wallet as a top-up (a "round-up"
    # style auto-save). 0 disables auto-save; the goal can still be
    # topped up manually.
    auto_save_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="e.g. 5.00 = save 5% of every SEND automatically.",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.goal_id:
            self.goal_id = f"GOAL-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def progress_percent(self):
        if self.target_amount <= 0:
            return 0
        pct = (self.savings_wallet.balance / self.target_amount) * 100
        return min(100, round(pct, 2))

    def __str__(self):
        return f"{self.name} ({self.user.phone})"


# =====================================================
# RATE ALERT / PRICE WATCH
# =====================================================

class PriceAlert(models.Model):

    alert_id = models.CharField(max_length=40, primary_key=True, editable=False)

    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='price_alerts')
    from_currency = models.CharField(max_length=10)
    to_currency = models.CharField(max_length=10)

    # Fire when 1 from_currency >= threshold_rate in to_currency
    # (e.g. from=BTC, to=BDT, threshold=6000000 -> alert when BTC
    # hits 60 lakh BDT or higher).
    threshold_rate = models.DecimalField(max_digits=24, decimal_places=8)

    is_active = models.BooleanField(default=True)
    triggered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.alert_id:
            self.alert_id = f"ALERT-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.from_currency}->{self.to_currency} >= {self.threshold_rate}"


# =====================================================
# MERCHANT PAYMENT LINKS
# =====================================================

class PaymentLink(models.Model):

    link_id = models.CharField(max_length=40, primary_key=True, editable=False)

    merchant = models.ForeignKey(
        'User', on_delete=models.CASCADE, related_name='payment_links'
    )
    receiving_wallet = models.ForeignKey(
        'Wallet', on_delete=models.CASCADE, related_name='payment_links'
    )

    title = models.CharField(max_length=100)
    # Null amount = payer chooses how much to pay (donation-style);
    # otherwise the link is fixed-amount (invoice-style).
    amount = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.link_id:
            self.link_id = secrets.token_urlsafe(8)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"PaymentLink({self.title}) - {self.merchant.phone}"


# =====================================================
# WEBAUTHN (BIOMETRIC / PASSKEY LOGIN)
#
# One row per registered authenticator (a phone's fingerprint sensor,
# a laptop's Face ID, a hardware key, etc.) — a user can have several.
# =====================================================

# NOTE: WebAuthn / biometric-passkey login was removed. If you ever
# want it back, restore the WebAuthnCredential model here plus the
# WebAuthn views/urls/admin entries (removed alongside it).
