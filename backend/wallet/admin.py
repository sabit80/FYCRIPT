from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    User, Role, UserRole, KYC, BankAccount, Currency, Wallet,
    CryptoAddress, ExchangeRate, Transaction, Notification,
    AuditLog, LoginSession, MoneyRequest, ScheduledPayment,
    GroupPayment, GroupPaymentParticipant, SavingsGoal, PriceAlert,
    PaymentLink,
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):

    model = User
    ordering = ['email']
    list_display = [
        'email', 'name', 'phone', 'status', 'is_staff',
        'two_factor_enabled', 'is_flagged', 'referral_code',
    ]
    list_filter = ['status', 'is_staff', 'is_flagged', 'two_factor_enabled']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('name', 'phone', 'status')}),
        ('Security', {'fields': (
            'two_factor_enabled', 'is_flagged', 'flagged_reason', 'flagged_at',
        )}),
        ('Referrals', {'fields': ('referral_code', 'referred_by')}),
        ('Permissions', {'fields': (
            'is_active', 'is_staff', 'is_superuser',
            'groups', 'user_permissions',
        )}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'phone', 'password1', 'password2'),
        }),
    )
    readonly_fields = ['referral_code']
    search_fields = ['email', 'name', 'phone', 'referral_code']


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['id', 'role_name']


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'assigned_at']
    search_fields = ['user__email', 'user__phone', 'role__role_name']


@admin.register(KYC)
class KYCAdmin(admin.ModelAdmin):
    list_display = ['user', 'verification_status', 'submission_date']
    list_filter = ['verification_status']
    search_fields = ['user__email', 'user__phone', 'nid_number', 'passport_number']


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['user', 'bank_name', 'account_number', 'created_at']
    search_fields = ['user__email', 'user__phone', 'bank_name', 'account_number']


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ['currency_name', 'type', 'symbol']
    list_filter = ['type']


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = [
        'wallet_id', 'name', 'user', 'currency', 'balance',
        'wallet_status', 'is_default_receive',
    ]
    list_filter = ['wallet_status', 'is_default_receive', 'currency']
    search_fields = ['wallet_id', 'name', 'user__email', 'user__phone']


@admin.register(CryptoAddress)
class CryptoAddressAdmin(admin.ModelAdmin):
    list_display = ['address_id', 'wallet', 'blockchain', 'public_address']
    search_fields = ['address_id', 'public_address', 'wallet__wallet_id']


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ['rate_id', 'from_curr', 'to_curr', 'rate', 'last_updated']
    list_filter = ['from_curr', 'to_curr']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_id', 'transaction_type', 'sender_wallet',
        'receiver_wallet', 'amount', 'status', 'date',
    ]
    list_filter = ['transaction_type', 'status']
    search_fields = ['transaction_id', 'sender_wallet__wallet_id', 'receiver_wallet__wallet_id']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'type', 'message', 'read_status', 'timestamp']
    list_filter = ['type', 'read_status']
    search_fields = ['user__email', 'user__phone', 'message']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'user', 'remarks', 'ip_address', 'timestamp']
    list_filter = ['action']
    search_fields = ['user__email', 'user__phone', 'action', 'remarks']


@admin.register(LoginSession)
class LoginSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'ip_address', 'device_info', 'login_time']
    search_fields = ['user__email', 'user__phone', 'ip_address']


@admin.register(MoneyRequest)
class MoneyRequestAdmin(admin.ModelAdmin):
    list_display = [
        'request_id', 'requester', 'payer', 'amount', 'status', 'created_at',
    ]
    list_filter = ['status']
    search_fields = ['request_id', 'requester__phone', 'payer__phone']


@admin.register(ScheduledPayment)
class ScheduledPaymentAdmin(admin.ModelAdmin):
    list_display = [
        'schedule_id', 'owner', 'sender_wallet', 'amount', 'frequency',
        'next_run_at', 'status',
    ]
    list_filter = ['frequency', 'status']
    search_fields = ['schedule_id', 'owner__phone', 'owner__email']


class GroupPaymentParticipantInline(admin.TabularInline):
    model = GroupPaymentParticipant
    extra = 0
    readonly_fields = ['transaction', 'paid_at']


@admin.register(GroupPayment)
class GroupPaymentAdmin(admin.ModelAdmin):
    list_display = [
        'group_payment_id', 'title', 'organizer', 'total_amount', 'status', 'created_at',
    ]
    list_filter = ['status']
    search_fields = ['group_payment_id', 'title', 'organizer__phone']
    inlines = [GroupPaymentParticipantInline]


@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = [
        'goal_id', 'user', 'name', 'target_amount', 'auto_save_percent', 'is_active',
    ]
    list_filter = ['is_active']
    search_fields = ['goal_id', 'user__phone', 'name']


@admin.register(PriceAlert)
class PriceAlertAdmin(admin.ModelAdmin):
    list_display = [
        'alert_id', 'user', 'from_currency', 'to_currency',
        'threshold_rate', 'is_active', 'triggered_at',
    ]
    list_filter = ['is_active', 'from_currency', 'to_currency']
    search_fields = ['alert_id', 'user__phone']


@admin.register(PaymentLink)
class PaymentLinkAdmin(admin.ModelAdmin):
    list_display = ['link_id', 'title', 'merchant', 'amount', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['link_id', 'title', 'merchant__phone']
