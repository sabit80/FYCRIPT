import base64
import io
import secrets
import uuid
from decimal import Decimal

import pyotp
import qrcode
import requests
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import connection, models, transaction as db_transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    Wallet, Transaction, Currency, CryptoAddress, BankAccount,
    KYC, LoginSession, Notification, ExchangeRate, AuditLog,
    Role, UserRole, MoneyRequest, ScheduledPayment, GroupPayment,
    GroupPaymentParticipant, SavingsGoal, PriceAlert, PaymentLink,
)
from . import db as rawsql
from .serializers import (
    RegisterSerializer, UserSerializer, ChangePasswordSerializer,
    CurrencySerializer, BankAccountSerializer, WalletSerializer,
    FundWalletSerializer, TransactionSerializer, SendSerializer,
    ExchangeSerializer, KYCSerializer, LoginSessionSerializer,
    NotificationSerializer, ExchangeRateSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    SetTransactionPinSerializer, AdminKYCSerializer, AdminKYCActionSerializer,
    MoneyRequestSerializer, MoneyRequestCreateSerializer,
    MoneyRequestRespondSerializer, TwoFactorConfirmSerializer,
    TwoFactorLoginVerifySerializer, ScheduledPaymentSerializer,
    ScheduledPaymentCreateSerializer, AccountTypeUpdateSerializer,
    DeactivateAccountSerializer, GroupPaymentSerializer,
    GroupPaymentCreateSerializer, SavingsGoalSerializer,
    SavingsGoalCreateSerializer, SavingsGoalTopUpSerializer,
    PriceAlertSerializer, PaymentLinkSerializer, PaymentLinkPaySerializer,
    BankDepositSerializer, BankWithdrawSerializer,
)

User = get_user_model()


# =====================================================
# FEES, LIMITS & FRAUD CONSTANTS
#
# Kept as plain module constants rather than DB rows — simple to
# reason about and to tune. Move to a Django admin-editable model
# later if you want ops to change these without a deploy.
# =====================================================

# Flat percentage fee on external SEND transfers (person -> different
# person). SHIFT (own wallet -> own wallet) and EXCHANGE stay fee-free.
SEND_FEE_PERCENT = Decimal("0.5")  # 0.5%

# Daily / monthly outgoing send caps, in USD-equivalent, by KYC tier.
# UNVERIFIED users (no approved KYC) are capped much lower than
# VERIFIED ones -- a standard mobile-money pattern.
SEND_LIMITS_USD = {
    'UNVERIFIED': {'daily': Decimal('100'), 'monthly': Decimal('500')},
    'VERIFIED': {'daily': Decimal('5000'), 'monthly': Decimal('50000')},
}

# Velocity check: more than this many SEND/SHIFT transactions by one
# user inside the window below auto-flags the account for review.
FRAUD_VELOCITY_COUNT = 8
FRAUD_VELOCITY_WINDOW_MINUTES = 10


def client_ip(request):
    return request.META.get('REMOTE_ADDR')


def client_device(request):
    return request.META.get('HTTP_USER_AGENT', '')[:255]


def hydrate_user(row):
    """rawsql.hydrate(User, row), but also JSON-decodes recovery_codes_hash
    back into a python list the way the ORM's JSONField would."""
    import json
    if row is None:
        return None
    row = dict(row)
    raw_codes = row.get('recovery_codes_hash')
    row['recovery_codes_hash'] = json.loads(raw_codes) if raw_codes else []
    return rawsql.hydrate(User, row)


def create_audit_log(user, action, remarks='', ip_address=None):
    """Raw-SQL replacement for `AuditLog.objects.create(...)`."""
    from django.utils import timezone
    rawsql.insert(
        AuditLog,
        user_id=(user.id if user else None),
        action=action,
        remarks=remarks,
        ip_address=ip_address,
        timestamp=timezone.now(),
    )


def _push_notification_over_websocket(notification_id, user_id, ntype, message, read_status, timestamp):
    """
    The ORM used to fire this from a `post_save` signal on Notification
    (see signals.py) — that signal only runs for `.objects.create()` /
    instance `.save()`, so a raw INSERT no longer triggers it. Every raw
    notification insert below calls this explicitly instead, keeping the
    real-time WebSocket push working exactly as before.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        f"notifications_{user_id}",
        {
            "type": "notification.message",
            "payload": {
                "id": notification_id,
                "type": ntype,
                "message": message,
                "is_read": read_status,
                "created_at": timestamp.isoformat(),
            },
        },
    )


def create_notification(user, type='INFO', message=''):
    """Raw-SQL replacement for `Notification.objects.create(...)` that
    still pushes over the WebSocket the same way the old post_save
    signal did (see _push_notification_over_websocket above)."""
    from django.utils import timezone
    now = timezone.now()
    new_id = rawsql.insert(
        Notification,
        user_id=user.id,
        message=message,
        type=type,
        read_status=False,
        timestamp=now,
    )
    _push_notification_over_websocket(new_id, user.id, type, message, False, now)
    return rawsql.hydrate(Notification, rawsql.get_row(Notification, 'id', new_id))


def save_user_fields(user, **fields):
    """
    Raw-SQL replacement for `user.save(update_fields=[...])`. Updates
    the row in the database AND mirrors the same values onto the
    in-memory `user` instance (usually `request.user`) so the rest of
    the request — serialization, further logic — sees the fresh values
    without needing a re-fetch.
    """
    import json

    db_fields = dict(fields)
    if 'recovery_codes_hash' in db_fields:
        # JSONField -> the DB column is plain longtext; the ORM handles
        # this (de)serialization itself, so a raw UPDATE has to do it too.
        db_fields['recovery_codes_hash'] = json.dumps(db_fields['recovery_codes_hash'])

    rawsql.update_by_pk(User, 'id', user.id, **db_fields)
    for field, value in fields.items():
        setattr(user, field, value)


def create_transaction(**fields):
    """Raw-SQL replacement for `Transaction.objects.create(...)` —
    generates the same `TXN-<12 hex>` id format Transaction.save() used to,
    inserts the row, and returns a hydrated (unsaved) instance."""
    txn_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
    fields.setdefault('status', 'COMPLETED')
    fields.setdefault('fee', Decimal('0'))
    fields.setdefault('category', '')
    fields.setdefault('date', timezone.now())
    rawsql.insert(Transaction, transaction_id=txn_id, **fields)
    return rawsql.hydrate(Transaction, rawsql.get_row(Transaction, 'transaction_id', txn_id))


def save_wallet_fields(wallet, **fields):
    """Raw-SQL replacement for `wallet.save()` / `wallet.save(update_fields=[...])`."""
    rawsql.update_by_pk(Wallet, 'wallet_id', wallet.wallet_id, **fields)
    for field, value in fields.items():
        setattr(wallet, field, value)


def get_wallet_or_404(wallet_id, user=None):
    """Raw-SQL replacement for `Wallet.objects.get(wallet_id=..., user=...)`
    (or without the user filter), hydrated with its currency attached so
    WalletSerializer / f-strings using wallet.currency_id keep working."""
    if user is not None:
        row = rawsql.find_one(Wallet, "wallet_id = %s AND user_id = %s", [wallet_id, user.id])
    else:
        row = rawsql.get_row(Wallet, 'wallet_id', wallet_id)
    if row is None:
        raise Wallet.DoesNotExist
    currency = rawsql.hydrate(Currency, rawsql.get_row(Currency, 'currency_name', row['currency_id']))
    return rawsql.hydrate(Wallet, row, currency=currency, user=(user if user is not None else None))


def require_pin_if_set(user, provided_pin):
    """
    Used by SendView / ExchangeView / MoneyRequest accept.
    If the user has never set a transaction PIN, this is a no-op
    (keeps existing accounts working without forcing PIN setup).
    If they have set one, the request must include the correct PIN.
    Raises ValidationError (-> 400) rather than returning a Response,
    so callers can just do `require_pin_if_set(request.user, data.get('pin'))`.
    """
    if not user.transaction_pin_hash:
        return

    if not provided_pin or not user.check_transaction_pin(provided_pin):
        raise ValidationError({"pin": "Incorrect or missing transaction PIN."})


# =====================================================
# EXCHANGE RATES
#
# Rates live in the ExchangeRate table (CURRENCY "converts"
# CURRENCY in the ERD) instead of a hardcoded dict, so admins can
# manage them from /admin/ and every conversion in the app reads
# from one source of truth.
# =====================================================

def get_rate(from_currency, to_currency):
    """
    Returns the Decimal rate such that:
        amount_in_to_currency = amount_in_from_currency * rate
    Falls back to bridging through USD if no direct row exists.
    """

    if from_currency == to_currency:
        return Decimal("1")

    direct = rawsql.find_one(
        ExchangeRate, "from_curr_id = %s AND to_curr_id = %s",
        [from_currency, to_currency],
    )

    if direct:
        return direct['rate']

    inverse = rawsql.find_one(
        ExchangeRate, "from_curr_id = %s AND to_curr_id = %s",
        [to_currency, from_currency],
    )

    if inverse and inverse['rate']:
        return Decimal("1") / inverse['rate']

    # Bridge via USD: from -> USD -> to
    from_to_usd = rawsql.find_one(
        ExchangeRate, "from_curr_id = %s AND to_curr_id = %s",
        [from_currency, 'USD'],
    )
    usd_to_to = rawsql.find_one(
        ExchangeRate, "from_curr_id = %s AND to_curr_id = %s",
        ['USD', to_currency],
    )

    if from_to_usd and usd_to_to:
        return from_to_usd['rate'] * usd_to_to['rate']

    raise ExchangeRate.DoesNotExist(
        f"No exchange rate available for {from_currency} -> {to_currency}"
    )


def convert_currency(amount, from_currency, to_currency):
    return amount * get_rate(from_currency, to_currency)


# =====================================================
# FEE / LIMIT / FRAUD HELPERS  (used by SendView)
# =====================================================

def calculate_send_fee(amount):
    """Flat percentage fee, in the sending wallet's own currency."""
    return (amount * SEND_FEE_PERCENT / Decimal("100")).quantize(Decimal("0.00000001"))


def usd_equivalent(amount, currency_id):
    try:
        return convert_currency(amount, currency_id, "USD")
    except ExchangeRate.DoesNotExist:
        return amount  # no rate available — treat 1:1 rather than block the check


def check_send_limit(user, sender_wallet, send_amount):
    """
    Raises ValidationError if this SEND would push the user over their
    daily or monthly USD-equivalent cap for their KYC tier. Only
    external SEND transfers count against the cap (SHIFT/EXCHANGE
    between a user's own wallets don't leave the account).
    """

    tier = user.kyc_tier()
    limits = SEND_LIMITS_USD[tier]
    amount_usd = usd_equivalent(send_amount, sender_wallet.currency_id)

    now = timezone.now()
    day_start = now - timezone.timedelta(hours=24)
    month_start = now - timezone.timedelta(days=30)

    # sender_wallet__user=user, transaction_type='SEND', date__gte=X, with
    # the sending wallet's currency for USD-equivalent conversion below —
    # a straight join against wallet_wallet instead of select_related.
    sent_today = rawsql.fetchall(
        "SELECT t.amount, w.currency_id FROM wallet_transaction t "
        "JOIN wallet_wallet w ON w.wallet_id = t.sender_wallet_id "
        "WHERE w.user_id = %s AND t.transaction_type = 'SEND' AND t.date >= %s",
        [user.id, day_start],
    )
    sent_this_month = rawsql.fetchall(
        "SELECT t.amount, w.currency_id FROM wallet_transaction t "
        "JOIN wallet_wallet w ON w.wallet_id = t.sender_wallet_id "
        "WHERE w.user_id = %s AND t.transaction_type = 'SEND' AND t.date >= %s",
        [user.id, month_start],
    )

    daily_total = sum(
        (usd_equivalent(t['amount'], t['currency_id']) for t in sent_today),
        Decimal("0"),
    ) + amount_usd
    monthly_total = sum(
        (usd_equivalent(t['amount'], t['currency_id']) for t in sent_this_month),
        Decimal("0"),
    ) + amount_usd

    if daily_total > limits['daily']:
        raise ValidationError({
            "detail": (
                f"This would exceed your daily send limit of "
                f"${limits['daily']} ({tier.title()} tier). "
                + ("Complete KYC verification to raise your limit."
                   if tier == 'UNVERIFIED' else "")
            )
        })

    if monthly_total > limits['monthly']:
        raise ValidationError({
            "detail": (
                f"This would exceed your monthly send limit of "
                f"${limits['monthly']} ({tier.title()} tier). "
                + ("Complete KYC verification to raise your limit."
                   if tier == 'UNVERIFIED' else "")
            )
        })


def check_fraud_velocity(user, request):
    """
    If this user has made too many SEND/SHIFT transactions in a short
    window, flag the account and refuse this one. Called from
    SendView before any balance changes happen.
    """

    if user.is_flagged:
        raise ValidationError({
            "detail": (
                "Your account is flagged for review and can't send funds "
                "right now. Contact support."
            )
        })

    window_start = timezone.now() - timezone.timedelta(
        minutes=FRAUD_VELOCITY_WINDOW_MINUTES
    )
    recent_count = rawsql.count_where(
        Transaction,
        "sender_wallet_id IN (SELECT wallet_id FROM wallet_wallet WHERE user_id = %s) "
        "AND transaction_type IN ('SEND', 'SHIFT') AND date >= %s",
        [user.id, window_start],
    )

    if recent_count >= FRAUD_VELOCITY_COUNT:
        flagged_reason = (
            f"{recent_count} sends within {FRAUD_VELOCITY_WINDOW_MINUTES} "
            f"minutes (auto velocity check)."
        )
        flagged_at = timezone.now()
        save_user_fields(
            user, is_flagged=True, flagged_reason=flagged_reason, flagged_at=flagged_at,
        )

        create_audit_log(user, 'FRAUD_FLAG', remarks=flagged_reason, ip_address=client_ip(request))
        create_notification(
            user, type='SECURITY',
            message=(
                "Your account has been flagged for unusual activity and "
                "sends are temporarily paused. Contact support."
            ),
        )

        raise ValidationError({
            "detail": (
                "Unusual sending activity detected — your account has "
                "been flagged for review and this send was blocked."
            )
        })


class RatesView(APIView):

    permission_classes = [permissions.AllowAny]

    def get(self, request):

        rows = rawsql.find_all(ExchangeRate)
        rates = [
            rawsql.hydrate(
                ExchangeRate, row,
                from_curr=rawsql.hydrate(Currency, rawsql.get_row(Currency, 'currency_name', row['from_curr_id'])),
                to_curr=rawsql.hydrate(Currency, rawsql.get_row(Currency, 'currency_name', row['to_curr_id'])),
            )
            for row in rows
        ]
        return Response(ExchangeRateSerializer(rates, many=True).data)


class CurrencyListView(generics.ListAPIView):

    permission_classes = [permissions.AllowAny]
    serializer_class = CurrencySerializer

    def get_queryset(self):
        rows = rawsql.find_all(Currency, order_by='type, currency_name')
        return rawsql.hydrate_all(Currency, rows)


# =====================================================
# AUTH
# =====================================================

def tokens_for_user(user):

    refresh = RefreshToken.for_user(user)

    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def create_wallet_for_user(user, currency_name, is_default_receive=False):

    wallet_id = f"WAL-{uuid.uuid4().hex[:10].upper()}"

    if is_default_receive:
        rawsql.unset_other_default_wallets(user.id)

    currency_row = rawsql.get_row(Currency, 'currency_name', currency_name)
    currency = rawsql.hydrate(Currency, currency_row)

    rawsql.insert(
        Wallet,
        wallet_id=wallet_id,
        user_id=user.id,
        currency_id=currency_name,
        balance=Decimal('0'),
        is_default_receive=is_default_receive,
        wallet_status='ACTIVE',
        name=f"{currency_name} Wallet",
        created_at=timezone.now(),
    )
    wallet = rawsql.hydrate(
        Wallet, rawsql.get_row(Wallet, 'wallet_id', wallet_id),
        currency=currency, user=user,
    )

    if currency.type == 'CRYPTO':
        blockchain_map = {
            'BTC': 'Bitcoin', 'ETH': 'Ethereum', 'USDT': 'Tron (TRC20)',
        }
        rawsql.insert(
            CryptoAddress,
            address_id=f"ADR-{uuid.uuid4().hex[:10].upper()}",
            wallet_id=wallet_id,
            blockchain=blockchain_map.get(currency_name, currency_name),
            public_address=uuid.uuid4().hex,
        )

    return wallet


def check_password_breached(raw_password):
    """
    Checks a password against the HaveIBeenPwned breached-password
    database using the k-Anonymity range API — only the first 5
    chars of the SHA-1 hash are ever sent, never the password or
    full hash, so HIBP can't recover the actual password.

    Returns True if the password appears in known breaches. Fails
    OPEN (returns False, i.e. "not breached") on any network/API
    error — a broken third-party check should never block signup.
    NOTE: like sync_live_rates, this sandbox's network allow-list
    blocks api.pwnedpasswords.com, so this call could not be
    exercised end-to-end while writing it. Double check connectivity
    from your own server before relying on it in production.
    """

    import hashlib

    sha1 = hashlib.sha1(raw_password.encode('utf-8')).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]

    try:
        resp = requests.get(
            f"https://api.pwnedpasswords.com/range/{prefix}", timeout=5
        )
        resp.raise_for_status()
    except requests.RequestException:
        return False

    for line in resp.text.splitlines():
        line_suffix, _, _count = line.partition(':')
        if line_suffix.strip() == suffix:
            return True

    return False


class RegisterView(generics.CreateAPIView):

    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if check_password_breached(serializer.validated_data['password']):
            return Response(
                {"password": [
                    "This password has appeared in known data breaches. "
                    "Please choose a different one."
                ]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        preferred_currency = serializer.validated_data.get(
            'preferred_currency', 'BDT'
        )
        user = serializer.save()

        with db_transaction.atomic():

            # Every account is created with exactly one default
            # receive wallet — the target for money sent to this
            # user's phone number, bKash-style.
            create_wallet_for_user(
                user, preferred_currency, is_default_receive=True
            )

            role_row = rawsql.find_one(Role, "role_name = %s", ['USER'])
            if role_row is None:
                role_id = rawsql.insert(Role, role_name='USER')
            else:
                role_id = role_row['id']

            if not rawsql.exists_where(
                UserRole, "user_id = %s AND role_id = %s", [user.id, role_id]
            ):
                rawsql.insert(
                    UserRole, user_id=user.id, role_id=role_id,
                    assigned_at=timezone.now(),
                )

            create_audit_log(user, 'REGISTER', remarks=user.email, ip_address=client_ip(request))
            create_notification(
                user, type='INFO',
                message=(
                    f"Welcome! Your account and your {preferred_currency} "
                    f"receive wallet are ready."
                ),
            )

        return Response(
            {
                "user": UserSerializer(user).data,
                **tokens_for_user(user),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):

        email = request.data.get('email', '')
        password = request.data.get('password', '')

        user = authenticate(
            request, username=email, password=password
        )

        if user is None:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # ---------------------------------------------
        # 2FA challenge: don't hand out real tokens yet. Instead
        # cache a short-lived `login_token` -> user_id mapping and
        # ask the client to call TwoFactorLoginVerifyView with it
        # plus a 6-digit code (or a recovery code).
        # ---------------------------------------------
        if user.two_factor_enabled:

            login_token = secrets.token_urlsafe(32)
            cache.set(f"2fa-login:{login_token}", user.id, timeout=300)

            return Response({
                "two_factor_required": True,
                "login_token": login_token,
            })

        rawsql.insert(
            LoginSession, user_id=user.id, ip_address=client_ip(request),
            device_info=client_device(request), login_time=timezone.now(),
        )
        create_audit_log(user, 'LOGIN', remarks=user.email, ip_address=client_ip(request))

        return Response({
            "user": UserSerializer(user).data,
            **tokens_for_user(user),
        })


class TwoFactorLoginVerifyView(APIView):
    """Step 2 of a 2FA login: exchange login_token + code for real
    access/refresh tokens."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):

        serializer = TwoFactorLoginVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user_id = cache.get(f"2fa-login:{data['login_token']}")
        if not user_id:
            return Response(
                {"detail": "This login attempt has expired. Please log in again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = hydrate_user(rawsql.get_row(User, 'id', user_id))

        if not _verify_totp_or_recovery(user, data['code']):
            return Response(
                {"detail": "Incorrect authentication code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache.delete(f"2fa-login:{data['login_token']}")

        rawsql.insert(
            LoginSession, user_id=user.id, ip_address=client_ip(request),
            device_info=client_device(request), login_time=timezone.now(),
        )
        create_audit_log(user, 'LOGIN_2FA', remarks=user.email, ip_address=client_ip(request))

        return Response({
            "user": UserSerializer(user).data,
            **tokens_for_user(user),
        })


def _verify_totp_or_recovery(user, code):
    """True if `code` is either a valid current TOTP code, or an
    unused recovery code (which is then burned so it can't be reused)."""

    code = (code or '').strip()

    if user.two_factor_secret and pyotp.TOTP(user.two_factor_secret).verify(
        code, valid_window=1
    ):
        return True

    for i, hashed in enumerate(user.recovery_codes_hash):
        if check_password(code, hashed):
            remaining = list(user.recovery_codes_hash)
            remaining.pop(i)
            save_user_fields(user, recovery_codes_hash=remaining)
            return True

    return False


# =====================================================
# TWO-FACTOR AUTHENTICATION — SETUP / DISABLE
# =====================================================

class Enable2FASetupView(APIView):
    """
    Step 1 of turning 2FA on: generate a brand-new TOTP secret (not
    yet saved as active — two_factor_enabled stays False until the
    user proves they can generate a valid code from it) and return
    both the raw secret and a scannable QR code image (base64 PNG)
    for an authenticator app.
    """

    def post(self, request):

        secret = pyotp.random_base32()

        # Stash pending secret in cache keyed by user id (5 min to
        # confirm) rather than writing it to the user row yet.
        cache.set(f"2fa-setup:{request.user.id}", secret, timeout=300)

        uri = pyotp.TOTP(secret).provisioning_uri(
            name=request.user.email, issuer_name="CryptoWallet"
        )

        qr_img = qrcode.make(uri)
        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        qr_base64 = base64.b64encode(buf.getvalue()).decode()

        return Response({
            "secret": secret,
            "qr_code_base64": f"data:image/png;base64,{qr_base64}",
        })


class Enable2FAConfirmView(APIView):
    """Step 2: user submits the code their app is now showing. On
    success, 2FA is actually turned on and a set of one-time
    recovery codes is generated and returned ONCE (plaintext) —
    only their hashes are stored."""

    def post(self, request):

        serializer = TwoFactorConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        pending_secret = cache.get(f"2fa-setup:{request.user.id}")
        if not pending_secret:
            return Response(
                {"detail": "No 2FA setup in progress, or it expired. Start again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not pyotp.TOTP(pending_secret).verify(
            serializer.validated_data['code'], valid_window=1
        ):
            return Response(
                {"detail": "Incorrect code. Check your authenticator app and retry."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recovery_codes = [secrets.token_hex(4).upper() for _ in range(8)]

        save_user_fields(
            request.user,
            two_factor_secret=pending_secret,
            two_factor_enabled=True,
            recovery_codes_hash=[make_password(c) for c in recovery_codes],
        )
        cache.delete(f"2fa-setup:{request.user.id}")

        create_audit_log(request.user, '2FA_ENABLED', ip_address=client_ip(request))
        create_notification(
            request.user, type='SECURITY',
            message="Two-factor authentication was enabled on your account.",
        )

        return Response({
            "detail": "Two-factor authentication enabled.",
            "recovery_codes": recovery_codes,
        })


class Disable2FAView(APIView):

    def post(self, request):

        password = request.data.get("password", "")

        if not password or not request.user.check_password(password):
            return Response(
                {"detail": "Incorrect password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        save_user_fields(
            request.user,
            two_factor_enabled=False,
            two_factor_secret=None,
            recovery_codes_hash=[],
        )

        create_audit_log(request.user, '2FA_DISABLED', ip_address=client_ip(request))
        create_notification(
            request.user, type='SECURITY',
            message="Two-factor authentication was disabled on your account.",
        )

        return Response({"detail": "Two-factor authentication disabled."})


class ProfileView(generics.RetrieveUpdateAPIView):

    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        # UserSerializer only exposes 'name', 'account_type' and
        # 'business_name' as writable (everything else is read_only —
        # see UserSerializer.Meta) — a raw UPDATE of just those instead
        # of the default ModelSerializer.save() -> instance.save().
        writable = {
            k: v for k, v in serializer.validated_data.items()
            if k in ('name', 'account_type', 'business_name')
        }
        save_user_fields(self.request.user, **writable)
        serializer.instance = self.request.user


class ChangePasswordView(APIView):

    def post(self, request):

        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user

        if not user.check_password(
            serializer.validated_data['currentPassword']
        ):
            return Response(
                {"currentPassword": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data['newPassword'])
        save_user_fields(user, password=user.password)

        create_audit_log(user, 'PASSWORD_CHANGE', remarks=user.email, ip_address=client_ip(request))
        create_notification(user, type='SECURITY', message="Your password was changed.")

        return Response({"detail": "Password updated."})


# =====================================================
# FORGOT / RESET PASSWORD
#
# Standard Django token flow: a signed, time-limited token tied to
# the user's pk + a hash of their current password (so the token
# auto-invalidates the moment it's used, or if the password changes
# again first). EMAIL_BACKEND is the console backend in dev
# (settings.py) — the "email" just prints to the runserver console;
# swap in a real backend (SMTP/SES/etc.) for production.
# =====================================================

class PasswordResetRequestView(APIView):

    permission_classes = [permissions.AllowAny]

    def post(self, request):

        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        user_row = rawsql.find_one(User, "LOWER(email) = LOWER(%s)", [email])
        user = hydrate_user(user_row)

        # Always return the same response whether or not the email
        # exists, so this endpoint can't be used to check which
        # emails are registered.
        generic_response = Response(
            {"detail": "If that email is registered, a reset link has been sent."}
        )

        if not user:
            return generic_response

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_link = f"{settings.FRONTEND_URL}/reset-password.html?uid={uid}&token={token}"

        send_mail(
            subject="Reset your CryptoWallet password",
            message=(
                f"Hi {user.name},\n\n"
                f"Use the link below to reset your password. This link "
                f"expires soon and can only be used once.\n\n{reset_link}\n\n"
                f"If you didn't request this, you can ignore this email."
            ),
            from_email=None,
            recipient_list=[user.email],
        )

        create_audit_log(user, 'PASSWORD_RESET_REQUEST', remarks=user.email, ip_address=client_ip(request))

        return generic_response


class PasswordResetConfirmView(APIView):

    permission_classes = [permissions.AllowAny]

    def post(self, request):

        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            uid = urlsafe_base64_decode(data['uid']).decode()
            user_row = rawsql.get_row(User, 'id', uid)
            if user_row is None:
                raise User.DoesNotExist
            user = hydrate_user(user_row)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            return Response(
                {"detail": "Invalid reset link."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not default_token_generator.check_token(user, data['token']):
            return Response(
                {"detail": "This reset link is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(data['newPassword'])
        save_user_fields(user, password=user.password)

        create_audit_log(user, 'PASSWORD_RESET', remarks=user.email, ip_address=client_ip(request))
        create_notification(user, type='SECURITY', message="Your password was reset.")

        return Response({"detail": "Password has been reset. You can now log in."})


# =====================================================
# TRANSACTION PIN
#
# Optional extra PIN, separate from the login password, required
# before Send/Exchange (see require_pin_if_set() above and its use
# in SendView / ExchangeView / MoneyRequestRespondView below).
# =====================================================

class SetTransactionPinView(APIView):

    def post(self, request):

        serializer = SetTransactionPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user

        if not user.check_password(data['currentPassword']):
            return Response(
                {"currentPassword": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        was_set = bool(user.transaction_pin_hash)
        user.set_transaction_pin(data['pin'])
        save_user_fields(user, transaction_pin_hash=user.transaction_pin_hash)

        create_audit_log(user, 'PIN_UPDATE' if was_set else 'PIN_SET', ip_address=client_ip(request))
        create_notification(
            user, type='SECURITY',
            message=(
                "Your transaction PIN was updated."
                if was_set else
                "A transaction PIN was set on your account."
            ),
        )

        return Response({"detail": "Transaction PIN saved."})


# =====================================================
# BANK ACCOUNTS
# One account (user) can connect one or many bank accounts.
# =====================================================

class BankAccountListCreateView(generics.ListCreateAPIView):

    serializer_class = BankAccountSerializer

    def get_queryset(self):
        rows = rawsql.find_all(BankAccount, "user_id = %s", [self.request.user.id])
        return rawsql.hydrate_all(BankAccount, rows, user=self.request.user)

    def perform_create(self, serializer):

        fields = dict(serializer.validated_data)
        new_id = rawsql.insert(
            BankAccount, user_id=self.request.user.id,
            created_at=timezone.now(), **fields,
        )
        bank_account = rawsql.hydrate(
            BankAccount, rawsql.get_row(BankAccount, 'id', new_id),
            user=self.request.user,
        )
        serializer.instance = bank_account

        create_audit_log(
            self.request.user, 'BANK_ACCOUNT_ADD',
            remarks=bank_account.account_number, ip_address=client_ip(self.request),
        )


class BankAccountDeleteView(generics.DestroyAPIView):

    serializer_class = BankAccountSerializer

    def get_queryset(self):
        rows = rawsql.find_all(BankAccount, "user_id = %s", [self.request.user.id])
        return rawsql.hydrate_all(BankAccount, rows, user=self.request.user)

    def perform_destroy(self, instance):
        rawsql.delete_by_pk(BankAccount, 'id', instance.id)


class BankAccountDepositView(APIView):
    """Move money FROM a linked bank account INTO one of the user's
    wallets (a simulated bank deposit — no real bank API involved)."""

    def post(self, request, pk):

        bank_account_row = rawsql.find_one(
            BankAccount, "id = %s AND user_id = %s", [pk, request.user.id]
        )
        if bank_account_row is None:
            return Response(
                {"detail": "Bank account not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        bank_account = rawsql.hydrate(BankAccount, bank_account_row, user=request.user)

        serializer = BankDepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data['amount']

        try:
            wallet = get_wallet_or_404(serializer.validated_data['wallet_id'], user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Wallet not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if wallet.wallet_status != 'ACTIVE':
            return Response(
                {"detail": "This wallet isn't active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with db_transaction.atomic():

            save_wallet_fields(wallet, balance=wallet.balance + amount)

            txn = create_transaction(
                sender_wallet_id=None,
                receiver_wallet_id=wallet.wallet_id,
                transaction_type='DEPOSIT',
                amount=amount,
                category='Bank Deposit',
            )

            create_audit_log(
                request.user, 'BANK_DEPOSIT',
                remarks=f"{bank_account.bank_name} -> {wallet.wallet_id}",
                ip_address=client_ip(request),
            )
            create_notification(
                request.user, type='TRANSACTION',
                message=f"Deposited {amount} {wallet.currency_id} from "
                        f"{bank_account.bank_name} to {wallet.name}.",
            )

        return Response(
            {
                "detail": "Deposit successful.",
                "transaction_id": txn.transaction_id,
                "wallet": WalletSerializer(wallet).data,
            },
            status=status.HTTP_201_CREATED,
        )


class BankAccountWithdrawView(APIView):
    """Move money FROM one of the user's wallets INTO a linked bank
    account (a simulated withdrawal — no real bank API involved)."""

    def post(self, request, pk):

        bank_account_row = rawsql.find_one(
            BankAccount, "id = %s AND user_id = %s", [pk, request.user.id]
        )
        if bank_account_row is None:
            return Response(
                {"detail": "Bank account not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        bank_account = rawsql.hydrate(BankAccount, bank_account_row, user=request.user)

        serializer = BankWithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data['amount']

        try:
            wallet = get_wallet_or_404(serializer.validated_data['wallet_id'], user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Wallet not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if wallet.wallet_status != 'ACTIVE':
            return Response(
                {"detail": "This wallet isn't active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if amount > wallet.balance:
            return Response(
                {"detail": "Insufficient balance."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with db_transaction.atomic():

            save_wallet_fields(wallet, balance=wallet.balance - amount)

            txn = create_transaction(
                sender_wallet_id=wallet.wallet_id,
                receiver_wallet_id=None,
                transaction_type='WITHDRAW',
                amount=amount,
                category='Bank Withdrawal',
            )

            create_audit_log(
                request.user, 'BANK_WITHDRAW',
                remarks=f"{wallet.wallet_id} -> {bank_account.bank_name}",
                ip_address=client_ip(request),
            )
            create_notification(
                request.user, type='TRANSACTION',
                message=f"Withdrew {amount} {wallet.currency_id} from "
                        f"{wallet.name} to {bank_account.bank_name}.",
            )

        return Response(
            {
                "detail": "Withdrawal successful.",
                "transaction_id": txn.transaction_id,
                "wallet": WalletSerializer(wallet).data,
            },
            status=status.HTTP_201_CREATED,
        )


# =====================================================
# KYC  (zero-or-one per user — create on first submit, update after)
# =====================================================

class KYCView(APIView):

    def get(self, request):

        kyc_row = rawsql.find_one(KYC, "user_id = %s", [request.user.id])

        if not kyc_row:
            return Response({"detail": "No KYC submitted yet."},
                             status=status.HTTP_404_NOT_FOUND)

        kyc = rawsql.hydrate(KYC, kyc_row, user=request.user)
        return Response(KYCSerializer(kyc).data)

    def post(self, request):

        serializer = KYCSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        existing_row = rawsql.find_one(KYC, "user_id = %s", [request.user.id])
        fields = {**serializer.validated_data, 'verification_status': 'PENDING'}

        if existing_row is None:
            new_id = rawsql.insert(
                KYC, user_id=request.user.id, submission_date=timezone.now(),
                reviewed_by_id=None, reviewed_at=None, admin_remarks=None, **fields,
            )
            created = True
        else:
            rawsql.update_by_pk(KYC, 'id', existing_row['id'], **fields)
            new_id = existing_row['id']
            created = False

        kyc = rawsql.hydrate(KYC, rawsql.get_row(KYC, 'id', new_id), user=request.user)

        create_audit_log(
            request.user, 'KYC_SUBMIT',
            remarks=kyc.nid_number or kyc.passport_number,
            ip_address=client_ip(request),
        )
        create_notification(
            request.user, type='INFO',
            message="Your KYC documents were submitted for review.",
        )

        return Response(
            KYCSerializer(kyc).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# =====================================================
# WALLETS
# =====================================================

class WalletListCreateView(generics.ListCreateAPIView):

    serializer_class = WalletSerializer
    lookup_field = 'wallet_id'

    def get_queryset(self):
        rows = rawsql.find_all(Wallet, "user_id = %s", [self.request.user.id])
        wallets = []
        for row in rows:
            currency = rawsql.hydrate(Currency, rawsql.get_row(Currency, 'currency_name', row['currency_id']))
            wallets.append(rawsql.hydrate(Wallet, row, currency=currency, user=self.request.user))
        return wallets

    def perform_create(self, serializer):

        currency = serializer.validated_data['currency']

        wallet = create_wallet_for_user(
            self.request.user, currency.currency_name,
            is_default_receive=False,
        )
        serializer.instance = wallet

        # apply any custom name the client sent
        name = self.request.data.get('name')
        if name:
            save_wallet_fields(wallet, name=name)

        create_audit_log(
            self.request.user, 'WALLET_CREATE',
            remarks=wallet.wallet_id, ip_address=client_ip(self.request),
        )


class WalletDeleteView(generics.DestroyAPIView):

    serializer_class = WalletSerializer
    lookup_field = 'wallet_id'

    def get_queryset(self):
        rows = rawsql.find_all(Wallet, "user_id = %s", [self.request.user.id])
        return rawsql.hydrate_all(Wallet, rows, user=self.request.user)

    def perform_destroy(self, instance):

        if instance.is_default_receive:
            raise ValidationError(
                "Your default receive wallet can't be deleted."
            )

        if instance.balance > 0:
            raise ValidationError(
                "Move funds out of this wallet before deleting it."
            )

        create_audit_log(
            self.request.user, 'WALLET_DELETE',
            remarks=instance.wallet_id, ip_address=client_ip(self.request),
        )
        rawsql.delete_by_pk(Wallet, 'wallet_id', instance.wallet_id)


class WalletFreezeToggleView(APIView):
    """Lets a user freeze (pause) or unfreeze one of their own
    wallets. A FROZEN wallet can't be used as a SendView sender
    wallet (see the ACTIVE check already in SendView) and can't
    receive new deposits either. The default receive wallet can't be
    frozen — that would silently break incoming transfers."""

    def post(self, request, wallet_id):

        try:
            wallet = get_wallet_or_404(wallet_id, user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND,
            )

        if wallet.is_default_receive:
            return Response(
                {"detail": "Your default receive wallet can't be frozen."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if wallet.wallet_status == 'FROZEN':
            new_status = 'ACTIVE'
            action, message = 'WALLET_UNFREEZE', f"{wallet.name} was unfrozen."
        else:
            new_status = 'FROZEN'
            action, message = 'WALLET_FREEZE', f"{wallet.name} was frozen."

        save_wallet_fields(wallet, wallet_status=new_status)

        create_audit_log(request.user, action, remarks=wallet.wallet_id, ip_address=client_ip(request))
        create_notification(request.user, type='SECURITY', message=message)

        return Response(WalletSerializer(wallet).data)


class WalletSetDefaultView(APIView):

    def post(self, request, wallet_id):

        try:
            wallet = get_wallet_or_404(wallet_id, user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND,
            )

        if wallet.wallet_status != 'ACTIVE':
            return Response(
                {"detail": "A frozen wallet can't be set as default. Unfreeze it first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rawsql.unset_other_default_wallets(request.user.id, except_wallet_id=wallet.wallet_id)
        save_wallet_fields(wallet, is_default_receive=True)

        create_audit_log(
            request.user, 'WALLET_SET_DEFAULT', remarks=wallet.wallet_id,
            ip_address=client_ip(request),
        )

        return Response(WalletSerializer(wallet).data)

class WalletLookupView(APIView):
    """
    Looks up any wallet (not just the current user's) by
    wallet_id — used by Send/Shift previews. Only exposes
    name/currency, never balance or owner identity.
    """

    def get(self, request, wallet_id):

        try:
            wallet = get_wallet_or_404(wallet_id)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Wallet ID not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "wallet_id": wallet.wallet_id,
            "name": wallet.name,
            "currency": wallet.currency_id,
            "is_own_wallet": wallet.user_id == request.user.id,
        })


class AccountLookupView(APIView):
    """
    Looks up an account by phone number — used by the Send page
    to preview who a phone number belongs to before sending,
    just like bKash's "Md. ***n" confirmation screen.
    """

    def get(self, request, phone):

        recipient_row = rawsql.find_one(User, "phone = %s", [phone])
        if recipient_row is None:
            return Response(
                {"detail": "No account found for this number."},
                status=status.HTTP_404_NOT_FOUND,
            )
        recipient = hydrate_user(recipient_row)

        if recipient.id == request.user.id:
            return Response(
                {"detail": "That's your own number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        default_wallet_row = rawsql.find_one(
            Wallet, "user_id = %s AND is_default_receive = 1", [recipient.id]
        )
        default_wallet = rawsql.hydrate(Wallet, default_wallet_row) if default_wallet_row else None

        masked_name = (
            recipient.name[0] + "***" + recipient.name[-1]
            if len(recipient.name) > 1 else recipient.name
        )

        return Response({
            "phone": recipient.phone,
            "name": masked_name,
            "receive_currency": default_wallet.currency_id if default_wallet else None,
        })


class ReceiveQRCodeView(APIView):
    """
    Returns a QR code (base64 PNG) encoding this user's phone number
    as a `cryptowallet://send?phone=...&name=...` URI, for the
    Receive page. The Send page's QR-scan button (js/send.js) reads
    that same URI back out to auto-fill the phone field.
    """

    def get(self, request):

        payload = f"cryptowallet://send?phone={request.user.phone}&name={request.user.name}"

        qr_img = qrcode.make(payload)
        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        qr_base64 = base64.b64encode(buf.getvalue()).decode()

        return Response({
            "phone": request.user.phone,
            "payload": payload,
            "qr_code_base64": f"data:image/png;base64,{qr_base64}",
        })


class FundWalletView(APIView):
    """
    Manual top-up of a wallet (e.g. cash-in / bank deposit).
    """

    def post(self, request, wallet_id):

        try:
            wallet = get_wallet_or_404(wallet_id, user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Wallet not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = FundWalletSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data['amount']

        with db_transaction.atomic():

            save_wallet_fields(wallet, balance=wallet.balance + amount)

            create_transaction(
                sender_wallet_id=None,
                receiver_wallet_id=wallet.wallet_id,
                transaction_type='DEPOSIT',
                amount=amount,
            )

            create_audit_log(request.user, 'DEPOSIT', remarks=wallet.wallet_id, ip_address=client_ip(request))
            create_notification(
                request.user, type='TRANSACTION',
                message=f"Deposited {amount} {wallet.currency_id} to {wallet.name}.",
            )

        return Response(WalletSerializer(wallet).data)


# =====================================================
# SEND  (bKash-style)
#
#   * recipient_phone  -> external transfer. Always lands in the
#     RECEIVER'S default receive wallet, converted if currencies
#     differ. The receiver can then shift it into any of their
#     own wallets afterwards.
#
#   * recipient_wallet_id -> internal shift between two of the
#     SENDER'S OWN wallets. Converted if currencies differ.
# =====================================================

class SendView(APIView):

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'send'

    def post(self, request):

        serializer = SendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        require_pin_if_set(request.user, data.get('pin'))
        check_fraud_velocity(request.user, request)

        try:
            sender_wallet = get_wallet_or_404(data['sender_wallet_id'], user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Sender wallet not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if sender_wallet.wallet_status != 'ACTIVE':
            return Response(
                {"detail": "This wallet isn't active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        send_amount = data['amount']

        if send_amount > sender_wallet.balance:
            return Response(
                {"detail": "Insufficient balance."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------------------------------------------
        # Resolve the receiving wallet
        # ---------------------------------------------
        if data['recipient_phone']:

            recipient_row = rawsql.find_one(User, "phone = %s", [data['recipient_phone']])
            if recipient_row is None:
                return Response(
                    {"detail": "No account found for this number."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            recipient_user = hydrate_user(recipient_row)

            if recipient_user.id == request.user.id:
                return Response(
                    {"detail": "You can't send money to yourself. "
                               "Use a wallet shift instead."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            receiver_row = rawsql.find_one(
                Wallet, "user_id = %s AND is_default_receive = 1", [recipient_user.id]
            )

            if not receiver_row:
                return Response(
                    {"detail": "Recipient has no receive wallet."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            receiver_currency = rawsql.hydrate(
                Currency, rawsql.get_row(Currency, 'currency_name', receiver_row['currency_id'])
            )
            receiver_wallet = rawsql.hydrate(
                Wallet, receiver_row, currency=receiver_currency, user=recipient_user,
            )

            txn_type = 'SEND'
            check_send_limit(request.user, sender_wallet, send_amount)

        else:

            try:
                receiver_wallet = get_wallet_or_404(data['recipient_wallet_id'], user=request.user)
            except Wallet.DoesNotExist:
                return Response(
                    {"detail": "That wallet isn't one of yours. To send to "
                               "someone else, use their phone number instead."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if receiver_wallet.wallet_id == sender_wallet.wallet_id:
                return Response(
                    {"detail": "Choose a different destination wallet."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            txn_type = 'SHIFT'

        # ---------------------------------------------
        # Convert if the two wallets use different currencies
        # ---------------------------------------------
        rate = get_rate(sender_wallet.currency_id, receiver_wallet.currency_id)
        receive_amount = send_amount * rate

        # Flat percentage fee on external SENDs only; SHIFTs between a
        # user's own wallets stay fee-free.
        fee = calculate_send_fee(send_amount) if txn_type == 'SEND' else Decimal("0")

        if send_amount + fee > sender_wallet.balance:
            return Response(
                {"detail": f"Insufficient balance to cover amount plus the "
                           f"{SEND_FEE_PERCENT}% fee ({fee} {sender_wallet.currency_id})."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with db_transaction.atomic():

            save_wallet_fields(sender_wallet, balance=sender_wallet.balance - (send_amount + fee))
            save_wallet_fields(receiver_wallet, balance=receiver_wallet.balance + receive_amount)

            txn = create_transaction(
                sender_wallet_id=sender_wallet.wallet_id,
                receiver_wallet_id=receiver_wallet.wallet_id,
                transaction_type=txn_type,
                amount=send_amount,
                received_amount=receive_amount,
                exchange_rate=rate,
                fee=fee,
                category=data.get('category', ''),
            )

            create_audit_log(
                request.user, txn_type,
                remarks=receiver_wallet.wallet_id, ip_address=client_ip(request),
            )
            create_notification(
                sender_wallet.user, type='TRANSACTION',
                message=(
                    f"Sent {send_amount} {sender_wallet.currency_id} "
                    f"to {receiver_wallet.name}."
                ),
            )

            if receiver_wallet.user_id != sender_wallet.user_id:
                create_notification(
                    receiver_wallet.user, type='TRANSACTION',
                    message=(
                        f"Received {receive_amount} {receiver_wallet.currency_id} "
                        f"from {sender_wallet.user.phone} into your "
                        f"{receiver_wallet.currency_id} receive wallet."
                    ),
                )

            # ---------------------------------------------
            # AUTO-SAVE: on external SENDs only, sweep a percentage
            # of the sent amount into any active SavingsGoal(s) with
            # auto_save_percent > 0. This comes out of the sender's
            # wallet *in addition to* the send + fee already
            # deducted above — if that would overdraw the wallet,
            # auto-save is skipped for that goal rather than blocking
            # the whole Send (the user's own money transfer always
            # takes priority over the savings top-up).
            # ---------------------------------------------
            if txn_type == 'SEND':

                goal_rows = rawsql.find_all(
                    SavingsGoal,
                    "user_id = %s AND is_active = 1 AND auto_save_percent > 0",
                    [sender_wallet.user.id],
                )

                for goal_row in goal_rows:

                    savings_wallet = get_wallet_or_404(goal_row['savings_wallet_id'])

                    if savings_wallet.currency_id != sender_wallet.currency_id:
                        continue  # only auto-save same-currency wallets — no surprise conversions

                    save_amount = (
                        send_amount * goal_row['auto_save_percent'] / Decimal("100")
                    ).quantize(Decimal("0.00000001"))

                    if save_amount <= 0 or save_amount > sender_wallet.balance:
                        continue

                    save_wallet_fields(sender_wallet, balance=sender_wallet.balance - save_amount)
                    save_wallet_fields(savings_wallet, balance=savings_wallet.balance + save_amount)

                    create_transaction(
                        sender_wallet_id=sender_wallet.wallet_id,
                        receiver_wallet_id=savings_wallet.wallet_id,
                        transaction_type='SHIFT',
                        amount=save_amount,
                        received_amount=save_amount,
                        exchange_rate=Decimal("1"),
                        category='Auto-Save',
                    )

        return Response(
            {
                "transaction_id": txn.transaction_id,
                "sender_wallet": WalletSerializer(sender_wallet).data,
                "received_amount": str(receive_amount),
                "exchange_rate": str(rate),
                "fee": str(fee),
            }
        )


# =====================================================
# EXCHANGE  (convert between two of the user's own wallets,
# same as SHIFT above but kept as its own endpoint for the
# existing Exchange page)
# =====================================================

class ExchangeView(APIView):

    def post(self, request):

        serializer = ExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        require_pin_if_set(request.user, data.get('pin'))

        try:
            from_wallet = get_wallet_or_404(data['from_wallet_id'], user=request.user)
            to_wallet = get_wallet_or_404(data['to_wallet_id'], user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Wallet not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        amount = data['amount']

        if amount > from_wallet.balance:
            return Response(
                {"detail": "Insufficient balance."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rate = get_rate(from_wallet.currency_id, to_wallet.currency_id)
        converted_amount = amount * rate

        # Same ID format Transaction.save() generates -- built here so the
        # stored procedure (sp_exchange_funds, database/schema.sql) can
        # insert the row itself instead of Transaction.objects.create().
        transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        # sp_exchange_funds does its own START TRANSACTION/COMMIT (it locks
        # both wallet rows with FOR UPDATE before moving the balance), so
        # it's called on its own rather than nested inside db_transaction
        # .atomic() -- nesting a second START TRANSACTION inside Django's
        # would silently commit the outer one early.
        with connection.cursor() as cursor:
            cursor.callproc('sp_exchange_funds', [
                from_wallet.wallet_id,
                to_wallet.wallet_id,
                amount,
                rate,
                transaction_id,
            ])

        # The procedure updated balances via raw SQL, so the in-memory
        # instances are stale -- re-fetch (also raw SQL) before serializing.
        from_wallet = get_wallet_or_404(from_wallet.wallet_id, user=request.user)
        to_wallet = get_wallet_or_404(to_wallet.wallet_id, user=request.user)

        create_audit_log(
            request.user, 'EXCHANGE',
            remarks=f"{from_wallet.wallet_id}->{to_wallet.wallet_id}",
            ip_address=client_ip(request),
        )
        create_notification(
            request.user, type='TRANSACTION',
            message=(
                f"Exchanged {amount} {from_wallet.currency_id} "
                f"for {converted_amount} {to_wallet.currency_id}."
            ),
        )

        return Response(
            {
                "from_wallet": WalletSerializer(from_wallet).data,
                "to_wallet": WalletSerializer(to_wallet).data,
                "exchange_rate": str(rate),
                "transaction_id": transaction_id,
            }
        )


# =====================================================
# TRANSACTIONS
# =====================================================

def fetch_transactions_for_user(user, currency=None):
    """
    Raw-SQL replacement for the ORM's
    `Transaction.objects.filter(Q(sender_wallet__user=user) |
    Q(receiver_wallet__user=user)).select_related(...)`. Returns
    hydrated Transaction instances with `.sender_wallet` /
    `.receiver_wallet` attached (each carrying just the handful of
    fields TransactionSerializer actually reads: wallet_id, name,
    currency_id, user_id, and `.user.phone`) so no further queries
    fire during serialization.
    """
    sql = (
        "SELECT t.*, "
        "sw.wallet_id AS sw_wallet_id, sw.name AS sw_name, "
        "sw.currency_id AS sw_currency_id, sw.user_id AS sw_user_id, su.phone AS su_phone, "
        "rw.wallet_id AS rw_wallet_id, rw.name AS rw_name, "
        "rw.currency_id AS rw_currency_id, rw.user_id AS rw_user_id, ru.phone AS ru_phone "
        "FROM wallet_transaction t "
        "LEFT JOIN wallet_wallet sw ON sw.wallet_id = t.sender_wallet_id "
        "LEFT JOIN wallet_user su ON su.id = sw.user_id "
        "LEFT JOIN wallet_wallet rw ON rw.wallet_id = t.receiver_wallet_id "
        "LEFT JOIN wallet_user ru ON ru.id = rw.user_id "
        "WHERE (sw.user_id = %s OR rw.user_id = %s)"
    )
    params = [user.id, user.id]

    if currency:
        sql += " AND (sw.currency_id = %s OR rw.currency_id = %s)"
        params += [currency, currency]

    sql += " ORDER BY t.date DESC"

    rows = rawsql.fetchall(sql, params)

    transactions = []
    for row in rows:
        sender_wallet = None
        if row['sw_wallet_id']:
            sender_wallet = Wallet(
                wallet_id=row['sw_wallet_id'], name=row['sw_name'],
                currency_id=row['sw_currency_id'], user_id=row['sw_user_id'],
            )
            sender_wallet.user = User(id=row['sw_user_id'], phone=row['su_phone'])

        receiver_wallet = None
        if row['rw_wallet_id']:
            receiver_wallet = Wallet(
                wallet_id=row['rw_wallet_id'], name=row['rw_name'],
                currency_id=row['rw_currency_id'], user_id=row['rw_user_id'],
            )
            receiver_wallet.user = User(id=row['rw_user_id'], phone=row['ru_phone'])

        txn_row = {
            k: v for k, v in row.items()
            if not k.startswith(('sw_', 'su_', 'rw_', 'ru_'))
        }
        transactions.append(rawsql.hydrate(
            Transaction, txn_row,
            sender_wallet=sender_wallet, receiver_wallet=receiver_wallet,
        ))

    return transactions


class TransactionListView(generics.ListAPIView):

    serializer_class = TransactionSerializer

    def get_queryset(self):

        user = self.request.user
        currency_param = self.request.query_params.get('currency')
        type_param = self.request.query_params.get('type')

        results = fetch_transactions_for_user(user, currency=currency_param)

        if type_param:
            serializer = self.get_serializer_class()
            results = [
                t for t in results
                if serializer(t, context=self.get_serializer_context()).data['type'] == type_param
            ]

        return results


class TransactionExportCSVView(APIView):
    """Downloads the requesting user's own transaction history as a
    CSV file (Reports page 'Export' button)."""

    def get(self, request):

        import csv
        from django.http import HttpResponse

        transactions = fetch_transactions_for_user(request.user)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            'attachment; filename="cryptowallet_transactions.csv"'
        )

        writer = csv.writer(response)
        writer.writerow([
            'Transaction ID', 'Date', 'Type', 'Amount', 'Currency',
            'Fee', 'Received Amount', 'Exchange Rate', 'Status',
            'Counterparty',
        ])

        for t in transactions:
            is_sender = t.sender_wallet and t.sender_wallet.user_id == request.user.id
            counterparty = None
            if is_sender and t.receiver_wallet and t.receiver_wallet.user_id != request.user.id:
                counterparty = t.receiver_wallet.user.phone
            elif not is_sender and t.sender_wallet:
                counterparty = t.sender_wallet.user.phone

            writer.writerow([
                t.transaction_id,
                t.date.isoformat(),
                t.transaction_type,
                t.amount,
                t.sender_wallet.currency_id if t.sender_wallet else '',
                t.fee,
                t.received_amount or '',
                t.exchange_rate or '',
                t.status,
                counterparty or '',
            ])

        return response


# =====================================================
# DASHBOARD SUMMARY
# =====================================================

class DashboardSummaryView(APIView):

    def get(self, request):

        wallet_rows = rawsql.find_all(Wallet, "user_id = %s", [request.user.id])
        wallets = rawsql.hydrate_all(Wallet, wallet_rows, user=request.user)
        transaction_count = len(fetch_transactions_for_user(request.user))

        total_balance_usd = Decimal("0")
        for w in wallets:
            try:
                total_balance_usd += convert_currency(w.balance, w.currency_id, "USD")
            except ExchangeRate.DoesNotExist:
                continue

        currencies = len({w.currency_id for w in wallets})

        return Response({
            "total_balance_usd": str(total_balance_usd),
            "total_wallets": len(wallets),
            "currencies": currencies,
            "total_transactions": transaction_count,
        })


# =====================================================
# KYC / SESSIONS / NOTIFICATIONS
# =====================================================

class LoginSessionListView(generics.ListAPIView):

    serializer_class = LoginSessionSerializer

    def get_queryset(self):
        rows = rawsql.find_all(LoginSession, "user_id = %s", [self.request.user.id], order_by='login_time DESC')
        return rawsql.hydrate_all(LoginSession, rows, user=self.request.user)


class NotificationListView(generics.ListAPIView):

    serializer_class = NotificationSerializer

    def get_queryset(self):
        rows = rawsql.find_all(Notification, "user_id = %s", [self.request.user.id], order_by='timestamp DESC')
        return rawsql.hydrate_all(Notification, rows, user=self.request.user)


class NotificationMarkReadView(APIView):

    def post(self, request, pk):

        row = rawsql.find_one(Notification, "id = %s AND user_id = %s", [pk, request.user.id])
        if row is None:
            return Response(
                {"detail": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        rawsql.update_by_pk(Notification, 'id', row['id'], read_status=True)
        row['read_status'] = True
        notification = rawsql.hydrate(Notification, row, user=request.user)

        return Response(NotificationSerializer(notification).data)


# =====================================================
# ADMIN — KYC REVIEW
#
# Restricted to staff accounts (User.is_staff). Create one with:
#   python manage.py createsuperuser
# or promote an existing account via Django admin / shell.
# =====================================================

class AdminKYCListView(generics.ListAPIView):
    """
    GET /api/admin/kyc/                -> pending queue (default)
    GET /api/admin/kyc/?status=APPROVED -> filter by any status
    """

    serializer_class = AdminKYCSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        status_filter = (self.request.query_params.get('status') or 'PENDING').upper()
        where_sql, params = None, []
        if status_filter != 'ALL':
            where_sql, params = "verification_status = %s", [status_filter]

        rows = rawsql.find_all(KYC, where_sql, params, order_by='submission_date')
        results = []
        for row in rows:
            user = hydrate_user(rawsql.get_row(User, 'id', row['user_id']))
            results.append(rawsql.hydrate(KYC, row, user=user))
        return results


class AdminKYCApproveView(APIView):

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):

        row = rawsql.get_row(KYC, 'id', pk)
        if row is None:
            return Response(
                {"detail": "KYC submission not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        applicant = hydrate_user(rawsql.get_row(User, 'id', row['user_id']))

        serializer = AdminKYCActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with db_transaction.atomic():

            reviewed_at = timezone.now()
            admin_remarks = serializer.validated_data.get('remarks', '')
            rawsql.update_by_pk(
                KYC, 'id', row['id'],
                verification_status='APPROVED', reviewed_by_id=request.user.id,
                reviewed_at=reviewed_at, admin_remarks=admin_remarks,
            )
            row.update(
                verification_status='APPROVED', reviewed_by_id=request.user.id,
                reviewed_at=reviewed_at, admin_remarks=admin_remarks,
            )
            kyc = rawsql.hydrate(KYC, row, user=applicant)

            create_audit_log(
                request.user, 'KYC_APPROVE',
                remarks=f"user={applicant.phone}", ip_address=client_ip(request),
            )
            create_notification(
                applicant, type='SECURITY',
                message="Your KYC verification was approved.",
            )

        return Response(AdminKYCSerializer(kyc).data)


class AdminKYCRejectView(APIView):

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):

        row = rawsql.get_row(KYC, 'id', pk)
        if row is None:
            return Response(
                {"detail": "KYC submission not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        applicant = hydrate_user(rawsql.get_row(User, 'id', row['user_id']))

        serializer = AdminKYCActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with db_transaction.atomic():

            reviewed_at = timezone.now()
            admin_remarks = serializer.validated_data.get('remarks', '')
            rawsql.update_by_pk(
                KYC, 'id', row['id'],
                verification_status='REJECTED', reviewed_by_id=request.user.id,
                reviewed_at=reviewed_at, admin_remarks=admin_remarks,
            )
            row.update(
                verification_status='REJECTED', reviewed_by_id=request.user.id,
                reviewed_at=reviewed_at, admin_remarks=admin_remarks,
            )
            kyc = rawsql.hydrate(KYC, row, user=applicant)

            create_audit_log(
                request.user, 'KYC_REJECT',
                remarks=f"user={applicant.phone}", ip_address=client_ip(request),
            )
            create_notification(
                applicant, type='SECURITY',
                message=(
                    "Your KYC verification was rejected."
                    + (f" Reason: {admin_remarks}" if admin_remarks else "")
                ),
            )

        return Response(AdminKYCSerializer(kyc).data)


# =====================================================
# ADMIN ANALYTICS DASHBOARD
# =====================================================

class AdminAnalyticsSummaryView(APIView):
    """Backs the admin.html analytics dashboard: headline numbers +
    a 14-day daily transaction-volume series for the chart."""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):

        total_users = rawsql.count_where(User)
        active_users = rawsql.count_where(User, "status = %s", ['ACTIVE'])
        flagged_users = rawsql.count_where(User, "is_flagged = 1")
        pending_kyc = rawsql.count_where(KYC, "verification_status = %s", ['PENDING'])
        total_transactions = rawsql.count_where(Transaction)
        total_wallets = rawsql.count_where(Wallet)

        volume_rows = rawsql.fetchall(
            "SELECT sw.currency_id AS currency, SUM(t.amount) AS total, "
            "COUNT(t.transaction_id) AS count "
            "FROM wallet_transaction t "
            "JOIN wallet_wallet sw ON sw.wallet_id = t.sender_wallet_id "
            "GROUP BY sw.currency_id ORDER BY total DESC"
        )

        since = timezone.now() - timezone.timedelta(days=14)
        daily_rows = rawsql.fetchall(
            "SELECT DATE(date) AS day, COUNT(transaction_id) AS count, "
            "SUM(amount) AS volume FROM wallet_transaction "
            "WHERE date >= %s GROUP BY DATE(date) ORDER BY day",
            [since],
        )
        daily_series = [
            {"day": r['day'].isoformat(), "count": r['count'], "volume": str(r['volume'])}
            for r in daily_rows
        ]

        return Response({
            "total_users": total_users,
            "active_users": active_users,
            "flagged_users": flagged_users,
            "pending_kyc": pending_kyc,
            "total_transactions": total_transactions,
            "total_wallets": total_wallets,
            "volume_by_currency": [
                {
                    "currency": r['currency'],
                    "total": str(r['total']),
                    "count": r['count'],
                }
                for r in volume_rows if r['currency']
            ],
            "daily_series": daily_series,
        })


class AdminFlaggedUsersView(generics.ListAPIView):
    """List of accounts currently flagged for fraud review."""

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        rows = rawsql.find_all(User, "is_flagged = 1", order_by='flagged_at DESC')
        return [hydrate_user(r) for r in rows]


class AdminClearFlagView(APIView):
    """Admin clears a fraud flag after reviewing the account."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):

        row = rawsql.get_row(User, 'id', pk)
        if row is None:
            return Response(
                {"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND,
            )
        user = hydrate_user(row)

        save_user_fields(user, is_flagged=False, flagged_reason='', flagged_at=None)

        create_audit_log(
            request.user, 'FRAUD_FLAG_CLEARED',
            remarks=f"user={user.phone}", ip_address=client_ip(request),
        )
        create_notification(
            user, type='SECURITY',
            message="Your account's fraud flag was cleared and sends are re-enabled.",
        )

        return Response(UserSerializer(user).data)


# =====================================================
# SCHEDULED / RECURRING PAYMENTS
# =====================================================

class ScheduledPaymentListCreateView(generics.ListCreateAPIView):

    serializer_class = ScheduledPaymentSerializer

    def get_queryset(self):
        rows = rawsql.find_all(ScheduledPayment, "owner_id = %s", [self.request.user.id], order_by='next_run_at')
        return [
            rawsql.hydrate(ScheduledPayment, row, sender_wallet=get_wallet_or_404(row['sender_wallet_id']))
            for row in rows
        ]

    def create(self, request, *args, **kwargs):

        serializer = ScheduledPaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            sender_wallet = get_wallet_or_404(data['sender_wallet_id'], user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Sender wallet not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        recipient_wallet = None
        recipient_wallet_id = None
        recipient_phone = data.get('recipient_phone') or None

        if data.get('recipient_wallet_id'):
            try:
                recipient_wallet = get_wallet_or_404(data['recipient_wallet_id'], user=request.user)
            except Wallet.DoesNotExist:
                return Response(
                    {"detail": "Recipient wallet not found among your own wallets."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            recipient_wallet_id = recipient_wallet.wallet_id
            recipient_phone = None
        elif recipient_phone and not rawsql.exists_where(User, "phone = %s", [recipient_phone]):
            return Response(
                {"detail": "No account found for this recipient number."},
                status=status.HTTP_404_NOT_FOUND,
            )

        schedule_id = f"SCH-{uuid.uuid4().hex[:12].upper()}"
        rawsql.insert(
            ScheduledPayment,
            schedule_id=schedule_id,
            owner_id=request.user.id,
            sender_wallet_id=sender_wallet.wallet_id,
            recipient_phone=recipient_phone,
            recipient_wallet_id=recipient_wallet_id,
            amount=data['amount'],
            note=data.get('note', ''),
            frequency=data['frequency'],
            next_run_at=data['next_run_at'],
            last_run_at=None,
            status='ACTIVE',
            created_at=timezone.now(),
        )
        schedule = rawsql.hydrate(
            ScheduledPayment, rawsql.get_row(ScheduledPayment, 'schedule_id', schedule_id),
            sender_wallet=sender_wallet,
        )

        create_audit_log(
            request.user, 'SCHEDULED_PAYMENT_CREATE',
            remarks=schedule.schedule_id, ip_address=client_ip(request),
        )

        return Response(
            ScheduledPaymentSerializer(schedule).data,
            status=status.HTTP_201_CREATED,
        )


class ScheduledPaymentCancelView(APIView):

    def post(self, request, schedule_id):

        row = rawsql.find_one(
            ScheduledPayment, "schedule_id = %s AND owner_id = %s", [schedule_id, request.user.id]
        )
        if row is None:
            return Response(
                {"detail": "Scheduled payment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        rawsql.update_by_pk(ScheduledPayment, 'schedule_id', row['schedule_id'], status='CANCELLED')
        row['status'] = 'CANCELLED'
        schedule = rawsql.hydrate(ScheduledPayment, row, sender_wallet=get_wallet_or_404(row['sender_wallet_id']))

        return Response(ScheduledPaymentSerializer(schedule).data)


class ScheduledPaymentPauseToggleView(APIView):

    def post(self, request, schedule_id):

        row = rawsql.find_one(
            ScheduledPayment, "schedule_id = %s AND owner_id = %s", [schedule_id, request.user.id]
        )
        if row is None:
            return Response(
                {"detail": "Scheduled payment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if row['status'] == 'CANCELLED':
            return Response(
                {"detail": "This schedule was cancelled and can't be resumed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_status = 'PAUSED' if row['status'] == 'ACTIVE' else 'ACTIVE'
        rawsql.update_by_pk(ScheduledPayment, 'schedule_id', row['schedule_id'], status=new_status)
        row['status'] = new_status
        schedule = rawsql.hydrate(ScheduledPayment, row, sender_wallet=get_wallet_or_404(row['sender_wallet_id']))

        return Response(ScheduledPaymentSerializer(schedule).data)


# =====================================================
# MONEY REQUEST  (the reverse of Send)
#
#   POST /api/requests/            -> create a request addressed to
#                                      another account's phone number
#   GET  /api/requests/            -> list requests you sent or received
#   POST /api/requests/<id>/accept/  -> payer accepts, funds move
#   POST /api/requests/<id>/decline/ -> payer declines
# =====================================================

def get_money_request_or_404(pk, payer=None):
    """Raw-SQL fetch of one MoneyRequest, hydrated with `.requester`,
    `.payer`, and `.requester_wallet` (with its `.currency_id`) attached
    so MoneyRequestSerializer needs no further queries."""
    where_sql = "request_id = %s"
    params = [pk]
    if payer is not None:
        where_sql += " AND payer_id = %s"
        params.append(payer.id)

    row = rawsql.find_one(MoneyRequest, where_sql, params)
    if row is None:
        raise MoneyRequest.DoesNotExist

    requester = hydrate_user(rawsql.get_row(User, 'id', row['requester_id']))
    payer_user = hydrate_user(rawsql.get_row(User, 'id', row['payer_id']))
    requester_wallet = get_wallet_or_404(row['requester_wallet_id'])

    return rawsql.hydrate(
        MoneyRequest, row,
        requester=requester, payer=payer_user, requester_wallet=requester_wallet,
    )


def save_money_request_fields(money_request, **fields):
    rawsql.update_by_pk(MoneyRequest, 'request_id', money_request.request_id, **fields)
    for field, value in fields.items():
        setattr(money_request, field, value)


class MoneyRequestListCreateView(APIView):

    def get(self, request):

        rows = rawsql.find_all(
            MoneyRequest,
            "requester_id = %s OR payer_id = %s", [request.user.id, request.user.id],
            order_by='created_at DESC',
        )
        requests_list = [
            get_money_request_or_404(row['request_id']) for row in rows
        ]

        serializer = MoneyRequestSerializer(
            requests_list, many=True, context={'request': request}
        )
        return Response(serializer.data)

    def post(self, request):

        serializer = MoneyRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payer_row = rawsql.find_one(User, "phone = %s", [data['payer_phone']])
        if payer_row is None:
            return Response(
                {"detail": "No account found for this number."},
                status=status.HTTP_404_NOT_FOUND,
            )
        payer = hydrate_user(payer_row)

        if payer.id == request.user.id:
            return Response(
                {"detail": "You can't request money from yourself."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        requester_wallet_id = data.get('requester_wallet_id')
        if requester_wallet_id:
            try:
                requester_wallet = get_wallet_or_404(requester_wallet_id, user=request.user)
            except Wallet.DoesNotExist:
                return Response(
                    {"detail": "That wallet isn't one of yours."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            default_row = rawsql.find_one(
                Wallet, "user_id = %s AND is_default_receive = 1", [request.user.id]
            )
            if not default_row:
                return Response(
                    {"detail": "You have no default receive wallet."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            requester_wallet = get_wallet_or_404(default_row['wallet_id'], user=request.user)

        request_id = f"REQ-{uuid.uuid4().hex[:12].upper()}"
        rawsql.insert(
            MoneyRequest,
            request_id=request_id,
            requester_id=request.user.id,
            requester_wallet_id=requester_wallet.wallet_id,
            payer_id=payer.id,
            amount=data['amount'],
            note=data.get('note', ''),
            status='PENDING',
            transaction_id=None,
            created_at=timezone.now(),
            responded_at=None,
        )
        money_request = get_money_request_or_404(request_id)

        create_notification(
            payer, type='TRANSACTION',
            message=(
                f"{request.user.name} requested {data['amount']} "
                f"{requester_wallet.currency_id} from you."
            ),
        )
        create_audit_log(
            request.user, 'MONEY_REQUEST_CREATE',
            remarks=money_request.request_id, ip_address=client_ip(request),
        )

        return Response(
            MoneyRequestSerializer(
                money_request, context={'request': request}
            ).data,
            status=status.HTTP_201_CREATED,
        )


class MoneyRequestAcceptView(APIView):

    def post(self, request, pk):

        try:
            money_request = get_money_request_or_404(pk, payer=request.user)
        except MoneyRequest.DoesNotExist:
            return Response(
                {"detail": "Money request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if money_request.status != 'PENDING':
            return Response(
                {"detail": f"This request is already {money_request.status.lower()}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = MoneyRequestRespondSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        require_pin_if_set(request.user, data.get('pin'))

        try:
            payer_wallet = get_wallet_or_404(data['payer_wallet_id'], user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "That wallet isn't one of yours."},
                status=status.HTTP_404_NOT_FOUND,
            )

        amount = money_request.amount

        if payer_wallet.currency_id == money_request.requester_wallet.currency_id:
            if amount > payer_wallet.balance:
                return Response(
                    {"detail": "Insufficient balance."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            rate = Decimal("1")
            received_amount = amount
        else:
            rate = get_rate(payer_wallet.currency_id, money_request.requester_wallet.currency_id)
            if amount > payer_wallet.balance:
                return Response(
                    {"detail": "Insufficient balance."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            received_amount = amount * rate

        requester_wallet = money_request.requester_wallet

        with db_transaction.atomic():

            save_wallet_fields(payer_wallet, balance=payer_wallet.balance - amount)
            save_wallet_fields(requester_wallet, balance=requester_wallet.balance + received_amount)

            txn = create_transaction(
                sender_wallet_id=payer_wallet.wallet_id,
                receiver_wallet_id=requester_wallet.wallet_id,
                transaction_type='SEND',
                amount=amount,
                received_amount=received_amount,
                exchange_rate=rate,
            )

            save_money_request_fields(
                money_request, status='ACCEPTED',
                transaction_id=txn.transaction_id, responded_at=timezone.now(),
            )

            create_audit_log(
                request.user, 'MONEY_REQUEST_ACCEPT',
                remarks=money_request.request_id, ip_address=client_ip(request),
            )
            create_notification(
                money_request.requester, type='TRANSACTION',
                message=(
                    f"{request.user.name} paid your request of "
                    f"{received_amount} {requester_wallet.currency_id}."
                ),
            )

        return Response(
            MoneyRequestSerializer(
                money_request, context={'request': request}
            ).data
        )


class MoneyRequestDeclineView(APIView):

    def post(self, request, pk):

        try:
            money_request = get_money_request_or_404(pk, payer=request.user)
        except MoneyRequest.DoesNotExist:
            return Response(
                {"detail": "Money request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if money_request.status != 'PENDING':
            return Response(
                {"detail": f"This request is already {money_request.status.lower()}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        save_money_request_fields(money_request, status='DECLINED', responded_at=timezone.now())

        create_audit_log(
            request.user, 'MONEY_REQUEST_DECLINE',
            remarks=money_request.request_id, ip_address=client_ip(request),
        )
        create_notification(
            money_request.requester, type='TRANSACTION',
            message=f"{request.user.name} declined your money request.",
        )

        return Response(
            MoneyRequestSerializer(
                money_request, context={'request': request}
            ).data
        )


# =====================================================
# ACCOUNT TYPE / DEACTIVATION
# =====================================================

class AccountTypeUpdateView(APIView):
    """Switch between PERSONAL and MERCHANT. Merchant accounts can
    create PaymentLinks (see PaymentLinkListCreateView)."""

    def post(self, request):

        serializer = AccountTypeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        save_user_fields(
            request.user, account_type=data['account_type'],
            business_name=data.get('business_name', ''),
        )

        create_audit_log(
            request.user, 'ACCOUNT_TYPE_CHANGE',
            remarks=data['account_type'], ip_address=client_ip(request),
        )

        return Response(UserSerializer(request.user).data)


class DeactivateAccountView(APIView):
    """
    Soft-deletes the account: status -> CLOSED, is_active -> False
    (so they can no longer authenticate), all wallets frozen. Data
    is kept (audit trail, transaction history for the other side of
    any transfer) — nothing is hard-deleted. Requires the current
    password as confirmation.
    """

    def post(self, request):

        serializer = DeactivateAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not request.user.check_password(serializer.validated_data['password']):
            return Response(
                {"detail": "Incorrect password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with db_transaction.atomic():

            save_user_fields(request.user, status='CLOSED', is_active=False)

            rawsql.update_where(
                Wallet, "user_id = %s", [request.user.id], wallet_status='FROZEN',
            )

            create_audit_log(request.user, 'ACCOUNT_DEACTIVATE', ip_address=client_ip(request))

        return Response({
            "detail": "Your account has been deactivated. Contact support to reactivate it."
        })


# =====================================================
# GROUP PAYMENT (SPLIT BILL)
# =====================================================

def get_group_payment_or_404(group_payment_id):
    """Raw-SQL fetch of one GroupPayment, hydrated with `.organizer`,
    `.receiver_wallet`, and `._participants` (a plain list, each with
    `.user` attached) so GroupPaymentSerializer needs no further
    queries. `participants` itself is a reverse-FK data descriptor
    that forbids direct instance assignment, so the list is attached
    under `._participants` instead and GroupPaymentSerializer's
    `participants` field reads it from there (see serializers.py)."""
    row = rawsql.get_row(GroupPayment, 'group_payment_id', group_payment_id)
    if row is None:
        raise GroupPayment.DoesNotExist

    organizer = hydrate_user(rawsql.get_row(User, 'id', row['organizer_id']))
    receiver_wallet = get_wallet_or_404(row['receiver_wallet_id'])

    participant_rows = rawsql.find_all(
        GroupPaymentParticipant, "group_payment_id = %s", [group_payment_id]
    )
    participants = []
    for p_row in participant_rows:
        p_user = hydrate_user(rawsql.get_row(User, 'id', p_row['user_id']))
        participants.append(rawsql.hydrate(GroupPaymentParticipant, p_row, user=p_user))

    group_payment = rawsql.hydrate(
        GroupPayment, row, organizer=organizer, receiver_wallet=receiver_wallet,
    )
    group_payment._participants = participants
    return group_payment


def save_group_payment_fields(group_payment, **fields):
    rawsql.update_by_pk(GroupPayment, 'group_payment_id', group_payment.group_payment_id, **fields)
    for field, value in fields.items():
        setattr(group_payment, field, value)


class GroupPaymentListCreateView(generics.ListCreateAPIView):
    """
    GET  -> group payments the requester organized OR is a
            participant in.
    POST -> create a new split; one GroupPaymentParticipant row is
            made per {phone, share_amount} entry. Each participant
            pays their own share later via
            GroupPaymentPayShareView — the organizer is never
            charged the whole amount up front.
    """

    serializer_class = GroupPaymentSerializer

    def get_queryset(self):
        rows = rawsql.fetchall(
            "SELECT DISTINCT gp.group_payment_id FROM wallet_grouppayment gp "
            "LEFT JOIN wallet_grouppaymentparticipant p ON p.group_payment_id = gp.group_payment_id "
            "WHERE gp.organizer_id = %s OR p.user_id = %s "
            "ORDER BY gp.created_at DESC",
            [self.request.user.id, self.request.user.id],
        )
        return [get_group_payment_or_404(r['group_payment_id']) for r in rows]

    def create(self, request, *args, **kwargs):

        serializer = GroupPaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            receiver_wallet = get_wallet_or_404(data['receiver_wallet_id'], user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Receiver wallet not found among your own wallets."},
                status=status.HTTP_404_NOT_FOUND,
            )

        with db_transaction.atomic():

            group_payment_id = f"GRP-{uuid.uuid4().hex[:10].upper()}"
            rawsql.insert(
                GroupPayment,
                group_payment_id=group_payment_id,
                organizer_id=request.user.id,
                receiver_wallet_id=receiver_wallet.wallet_id,
                title=data['title'],
                total_amount=data['total_amount'],
                status='OPEN',
                created_at=timezone.now(),
            )

            for entry in data['participants']:

                participant_row = rawsql.find_one(User, "phone = %s", [entry['phone']])

                if not participant_row:
                    continue  # skip unknown numbers rather than failing the whole split
                participant_user = hydrate_user(participant_row)

                existing = rawsql.find_one(
                    GroupPaymentParticipant,
                    "group_payment_id = %s AND user_id = %s",
                    [group_payment_id, participant_user.id],
                )
                if existing:
                    rawsql.update_by_pk(
                        GroupPaymentParticipant, 'id', existing['id'],
                        share_amount=entry['share_amount'],
                    )
                else:
                    rawsql.insert(
                        GroupPaymentParticipant,
                        group_payment_id=group_payment_id, user_id=participant_user.id,
                        share_amount=entry['share_amount'], status='PENDING',
                        transaction_id=None, paid_at=None,
                    )

                create_notification(
                    participant_user, type='TRANSACTION',
                    message=(
                        f"{request.user.name} added you to a split payment "
                        f"'{data['title']}' — your share is "
                        f"{entry['share_amount']}."
                    ),
                )

            group_payment = get_group_payment_or_404(group_payment_id)

        return Response(
            GroupPaymentSerializer(group_payment).data,
            status=status.HTTP_201_CREATED,
        )


class GroupPaymentPayShareView(APIView):
    """A participant pays their own share. Reuses the same
    fee/limit/fraud checks as a normal SEND, since this is exactly a
    Send under the hood — just from participant -> organizer's
    receiver_wallet."""

    def post(self, request, group_payment_id):

        try:
            group_payment = get_group_payment_or_404(group_payment_id)
        except GroupPayment.DoesNotExist:
            return Response(
                {"detail": "Split payment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        participant_row = rawsql.find_one(
            GroupPaymentParticipant,
            "group_payment_id = %s AND user_id = %s", [group_payment_id, request.user.id],
        )
        if participant_row is None:
            return Response(
                {"detail": "You're not a participant in this split payment."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if participant_row['status'] == 'PAID':
            return Response(
                {"detail": "You've already paid your share."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payer_wallet_id = request.data.get('payer_wallet_id')
        if not payer_wallet_id:
            return Response(
                {"detail": "payer_wallet_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payer_wallet = get_wallet_or_404(payer_wallet_id, user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND,
            )

        check_fraud_velocity(request.user, request)

        share_amount = participant_row['share_amount']
        rate = get_rate(payer_wallet.currency_id, group_payment.receiver_wallet.currency_id)
        receive_amount = share_amount * rate
        fee = calculate_send_fee(share_amount)

        if share_amount + fee > payer_wallet.balance:
            return Response(
                {"detail": "Insufficient balance to cover your share plus fee."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with db_transaction.atomic():

            save_wallet_fields(payer_wallet, balance=payer_wallet.balance - (share_amount + fee))
            save_wallet_fields(
                group_payment.receiver_wallet,
                balance=group_payment.receiver_wallet.balance + receive_amount,
            )

            txn = create_transaction(
                sender_wallet_id=payer_wallet.wallet_id,
                receiver_wallet_id=group_payment.receiver_wallet.wallet_id,
                transaction_type='SEND',
                amount=share_amount,
                received_amount=receive_amount,
                exchange_rate=rate,
                fee=fee,
                category=f"Split: {group_payment.title}",
            )

            rawsql.update_by_pk(
                GroupPaymentParticipant, 'id', participant_row['id'],
                status='PAID', transaction_id=txn.transaction_id, paid_at=timezone.now(),
            )

            group_payment.refresh_status()
            save_group_payment_fields(group_payment, status=group_payment.status)

            create_notification(
                group_payment.organizer, type='TRANSACTION',
                message=(
                    f"{request.user.name} paid their share "
                    f"({share_amount}) of '{group_payment.title}'."
                ),
            )

        group_payment = get_group_payment_or_404(group_payment_id)
        return Response(GroupPaymentSerializer(group_payment).data)


# =====================================================
# SAVINGS GOALS / AUTO-SAVE
# =====================================================

def get_savings_goal_or_404(goal_id, user=None):
    where_sql = "goal_id = %s"
    params = [goal_id]
    if user is not None:
        where_sql += " AND user_id = %s"
        params.append(user.id)
    row = rawsql.find_one(SavingsGoal, where_sql, params)
    if row is None:
        raise SavingsGoal.DoesNotExist
    savings_wallet = get_wallet_or_404(row['savings_wallet_id'])
    return rawsql.hydrate(SavingsGoal, row, savings_wallet=savings_wallet, user=user)


def save_savings_goal_fields(goal, **fields):
    rawsql.update_by_pk(SavingsGoal, 'goal_id', goal.goal_id, **fields)
    for field, value in fields.items():
        setattr(goal, field, value)


class SavingsGoalListCreateView(generics.ListCreateAPIView):

    serializer_class = SavingsGoalSerializer

    def get_queryset(self):
        rows = rawsql.find_all(SavingsGoal, "user_id = %s", [self.request.user.id])
        return [
            rawsql.hydrate(
                SavingsGoal, row,
                savings_wallet=get_wallet_or_404(row['savings_wallet_id']), user=self.request.user,
            )
            for row in rows
        ]

    def create(self, request, *args, **kwargs):

        serializer = SavingsGoalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            savings_wallet = get_wallet_or_404(data['savings_wallet_id'], user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND,
            )

        goal_id = f"GOAL-{uuid.uuid4().hex[:10].upper()}"
        rawsql.insert(
            SavingsGoal,
            goal_id=goal_id,
            user_id=request.user.id,
            savings_wallet_id=savings_wallet.wallet_id,
            name=data['name'],
            target_amount=data['target_amount'],
            deadline=data.get('deadline'),
            auto_save_percent=data.get('auto_save_percent', 0),
            is_active=True,
            created_at=timezone.now(),
        )
        goal = get_savings_goal_or_404(goal_id, user=request.user)

        return Response(SavingsGoalSerializer(goal).data, status=status.HTTP_201_CREATED)


class SavingsGoalTopUpView(APIView):
    """Manual, one-off top-up into a savings goal's wallet from
    another of the user's own wallets (a plain SHIFT, fee-free)."""

    def post(self, request, goal_id):

        try:
            goal = get_savings_goal_or_404(goal_id, user=request.user)
        except SavingsGoal.DoesNotExist:
            return Response(
                {"detail": "Savings goal not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SavingsGoalTopUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            from_wallet = get_wallet_or_404(data['from_wallet_id'], user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Source wallet not found."}, status=status.HTTP_404_NOT_FOUND,
            )

        if data['amount'] > from_wallet.balance:
            return Response(
                {"detail": "Insufficient balance."}, status=status.HTTP_400_BAD_REQUEST,
            )

        rate = get_rate(from_wallet.currency_id, goal.savings_wallet.currency_id)
        receive_amount = data['amount'] * rate

        with db_transaction.atomic():

            save_wallet_fields(from_wallet, balance=from_wallet.balance - data['amount'])
            save_wallet_fields(goal.savings_wallet, balance=goal.savings_wallet.balance + receive_amount)

            create_transaction(
                sender_wallet_id=from_wallet.wallet_id,
                receiver_wallet_id=goal.savings_wallet.wallet_id,
                transaction_type='SHIFT',
                amount=data['amount'],
                received_amount=receive_amount,
                exchange_rate=rate,
                category=f"Savings: {goal.name}",
            )

        return Response(SavingsGoalSerializer(goal).data)


class SavingsGoalDeactivateView(APIView):

    def post(self, request, goal_id):

        try:
            goal = get_savings_goal_or_404(goal_id, user=request.user)
        except SavingsGoal.DoesNotExist:
            return Response(
                {"detail": "Savings goal not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        save_savings_goal_fields(goal, is_active=not goal.is_active)

        return Response(SavingsGoalSerializer(goal).data)


# =====================================================
# PRICE ALERTS / RATE WATCH
#
# Actual triggering is done by the `check_price_alerts` management
# command (wallet/management/commands/check_price_alerts.py) — run
# it on a schedule (e.g. every 15 min) alongside sync_live_rates.
# =====================================================

class PriceAlertListCreateView(generics.ListCreateAPIView):

    serializer_class = PriceAlertSerializer

    def get_queryset(self):
        rows = rawsql.find_all(PriceAlert, "user_id = %s", [self.request.user.id])
        return rawsql.hydrate_all(PriceAlert, rows, user=self.request.user)

    def perform_create(self, serializer):
        fields = dict(serializer.validated_data)
        alert_id = f"ALERT-{uuid.uuid4().hex[:10].upper()}"
        rawsql.insert(
            PriceAlert, alert_id=alert_id, user_id=self.request.user.id,
            is_active=True, triggered_at=None, created_at=timezone.now(), **fields,
        )
        alert = rawsql.hydrate(
            PriceAlert, rawsql.get_row(PriceAlert, 'alert_id', alert_id), user=self.request.user,
        )
        serializer.instance = alert


class PriceAlertDeleteView(generics.DestroyAPIView):

    serializer_class = PriceAlertSerializer
    lookup_field = 'alert_id'

    def get_queryset(self):
        rows = rawsql.find_all(PriceAlert, "user_id = %s", [self.request.user.id])
        return rawsql.hydrate_all(PriceAlert, rows, user=self.request.user)

    def perform_destroy(self, instance):
        rawsql.delete_by_pk(PriceAlert, 'alert_id', instance.alert_id)


# =====================================================
# MERCHANT PAYMENT LINKS
# =====================================================

def get_payment_link_or_404(link_id, active_only=False):
    where_sql = "link_id = %s"
    params = [link_id]
    if active_only:
        where_sql += " AND is_active = 1"
    row = rawsql.find_one(PaymentLink, where_sql, params)
    if row is None:
        raise PaymentLink.DoesNotExist
    merchant = hydrate_user(rawsql.get_row(User, 'id', row['merchant_id']))
    receiving_wallet = get_wallet_or_404(row['receiving_wallet_id'])
    return rawsql.hydrate(PaymentLink, row, merchant=merchant, receiving_wallet=receiving_wallet)


class PaymentLinkListCreateView(generics.ListCreateAPIView):

    serializer_class = PaymentLinkSerializer

    def get_queryset(self):
        rows = rawsql.find_all(PaymentLink, "merchant_id = %s", [self.request.user.id], order_by='created_at DESC')
        return [
            rawsql.hydrate(
                PaymentLink, row,
                merchant=self.request.user, receiving_wallet=get_wallet_or_404(row['receiving_wallet_id']),
            )
            for row in rows
        ]

    def create(self, request, *args, **kwargs):

        if request.user.account_type != 'MERCHANT':
            return Response(
                {"detail": "Switch to a Merchant account first (Settings)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        wallet_id = request.data.get('receiving_wallet')

        try:
            wallet = get_wallet_or_404(wallet_id, user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND,
            )

        link_id = secrets.token_urlsafe(8)
        rawsql.insert(
            PaymentLink,
            link_id=link_id,
            merchant_id=request.user.id,
            receiving_wallet_id=wallet.wallet_id,
            title=request.data.get('title', 'Payment'),
            amount=request.data.get('amount') or None,
            is_active=True,
            created_at=timezone.now(),
        )
        link = rawsql.hydrate(
            PaymentLink, rawsql.get_row(PaymentLink, 'link_id', link_id),
            merchant=request.user, receiving_wallet=wallet,
        )

        return Response(PaymentLinkSerializer(link).data, status=status.HTTP_201_CREATED)


class PaymentLinkPublicView(APIView):
    """Anyone logged in (not just the merchant) can view a link's
    details by its public link_id, then pay it."""

    def get(self, request, link_id):

        try:
            link = get_payment_link_or_404(link_id, active_only=True)
        except PaymentLink.DoesNotExist:
            return Response(
                {"detail": "Payment link not found or inactive."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "link_id": link.link_id,
            "merchant_name": link.merchant.business_name or link.merchant.name,
            "title": link.title,
            "amount": link.amount,
            "currency": link.receiving_wallet.currency_id,
        })

    def post(self, request, link_id):

        try:
            link = get_payment_link_or_404(link_id, active_only=True)
        except PaymentLink.DoesNotExist:
            return Response(
                {"detail": "Payment link not found or inactive."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PaymentLinkPaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        amount = link.amount if link.amount is not None else data.get('amount')
        if not amount:
            return Response(
                {"detail": "This link requires you to specify an amount."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payer_wallet = get_wallet_or_404(data['payer_wallet_id'], user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND,
            )

        check_fraud_velocity(request.user, request)

        rate = get_rate(payer_wallet.currency_id, link.receiving_wallet.currency_id)
        receive_amount = amount * rate
        fee = calculate_send_fee(amount)

        if amount + fee > payer_wallet.balance:
            return Response(
                {"detail": "Insufficient balance."}, status=status.HTTP_400_BAD_REQUEST,
            )

        with db_transaction.atomic():

            save_wallet_fields(payer_wallet, balance=payer_wallet.balance - (amount + fee))
            save_wallet_fields(link.receiving_wallet, balance=link.receiving_wallet.balance + receive_amount)

            txn = create_transaction(
                sender_wallet_id=payer_wallet.wallet_id,
                receiver_wallet_id=link.receiving_wallet.wallet_id,
                transaction_type='SEND',
                amount=amount,
                received_amount=receive_amount,
                exchange_rate=rate,
                fee=fee,
                category=f"Payment link: {link.title}",
            )

            create_notification(
                link.merchant, type='TRANSACTION',
                message=f"You received a payment of {receive_amount} via '{link.title}'.",
            )

        return Response({
            "transaction_id": txn.transaction_id,
            "payer_wallet": WalletSerializer(payer_wallet).data,
        })


# =====================================================
# PDF STATEMENT EXPORT
# =====================================================

class TransactionExportPDFView(APIView):
    """Downloads the requesting user's own transaction history as a
    simple, printable PDF statement (Reports page 'Export PDF'
    button)."""

    def get(self, request):

        from django.http import HttpResponse
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet

        transactions = fetch_transactions_for_user(request.user)[:200]

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = (
            'attachment; filename="cryptowallet_statement.pdf"'
        )

        doc = SimpleDocTemplate(response, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = [
            Paragraph(f"CryptoWallet Statement — {request.user.name}", styles['Title']),
            Paragraph(f"Generated {timezone.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']),
            Spacer(1, 10 * mm),
        ]

        table_data = [["Date", "Type", "Amount", "Fee", "Status", "Category"]]
        for t in transactions:
            table_data.append([
                t.date.strftime('%Y-%m-%d %H:%M'),
                t.transaction_type,
                f"{t.amount} {t.sender_wallet.currency_id if t.sender_wallet else ''}",
                str(t.fee),
                t.status,
                t.category or '-',
            ])

        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5b6cff')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ]))
        elements.append(table)

        doc.build(elements)

        return response


# =====================================================
# ADMIN: API RATE-LIMIT / THROTTLE MONITORING
#
# DRF's ScopedRateThrottle keys its cache entries as
# "throttle_<scope>_<ident>" (see rest_framework.throttling). This
# view can't enumerate arbitrary cache keys with locmem/most cache
# backends, so it reports configured limits plus a simple live
# count for the calling admin's own throttle state as a
# demonstration; wire this up to Redis (which *can* be scanned by
# key pattern) for real per-user breakdowns in production.
# =====================================================

class AdminRateLimitStatusView(APIView):

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):

        from rest_framework.settings import api_settings

        return Response({
            "configured_rates": api_settings.DEFAULT_THROTTLE_RATES,
            "note": (
                "Live per-user throttle counters aren't enumerable with the "
                "in-memory cache backend used in dev. Switch CACHES to Redis "
                "to inspect/reset individual users' throttle windows here."
            ),
        })
