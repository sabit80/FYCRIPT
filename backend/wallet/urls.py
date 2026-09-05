from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [

    # AUTH
    path('auth/register/', views.RegisterView.as_view()),
    path('auth/login/', views.LoginView.as_view()),
    path('auth/login/verify-2fa/', views.TwoFactorLoginVerifyView.as_view()),
    path('auth/token/refresh/', TokenRefreshView.as_view()),
    path('auth/password-reset/request/', views.PasswordResetRequestView.as_view()),
    path('auth/password-reset/confirm/', views.PasswordResetConfirmView.as_view()),

    # PROFILE
    path('profile/', views.ProfileView.as_view()),
    path('profile/change-password/', views.ChangePasswordView.as_view()),
    path('profile/transaction-pin/', views.SetTransactionPinView.as_view()),

    # TWO-FACTOR AUTHENTICATION
    path('profile/2fa/setup/', views.Enable2FASetupView.as_view()),
    path('profile/2fa/confirm/', views.Enable2FAConfirmView.as_view()),
    path('profile/2fa/disable/', views.Disable2FAView.as_view()),

    # BANK ACCOUNTS
    path('bank-accounts/', views.BankAccountListCreateView.as_view()),
    path('bank-accounts/<int:pk>/', views.BankAccountDeleteView.as_view()),
    path('bank-accounts/<int:pk>/deposit/', views.BankAccountDepositView.as_view()),
    path('bank-accounts/<int:pk>/withdraw/', views.BankAccountWithdrawView.as_view()),

    # KYC
    path('kyc/', views.KYCView.as_view()),

    # ADMIN — KYC REVIEW
    path('admin/kyc/', views.AdminKYCListView.as_view()),
    path('admin/kyc/<int:pk>/approve/', views.AdminKYCApproveView.as_view()),
    path('admin/kyc/<int:pk>/reject/', views.AdminKYCRejectView.as_view()),

    # ADMIN — ANALYTICS & FRAUD
    path('admin/analytics/summary/', views.AdminAnalyticsSummaryView.as_view()),
    path('admin/flagged-users/', views.AdminFlaggedUsersView.as_view()),
    path('admin/flagged-users/<int:pk>/clear/', views.AdminClearFlagView.as_view()),

    # CURRENCIES / RATES
    path('currencies/', views.CurrencyListView.as_view()),
    path('rates/', views.RatesView.as_view()),

    # WALLETS
    path('wallets/', views.WalletListCreateView.as_view()),
    path('wallets/lookup/<str:wallet_id>/', views.WalletLookupView.as_view()),
    path('wallets/<str:wallet_id>/', views.WalletDeleteView.as_view()),
    path('wallets/<str:wallet_id>/fund/', views.FundWalletView.as_view()),
    path('wallets/<str:wallet_id>/freeze-toggle/', views.WalletFreezeToggleView.as_view()),
    path('wallets/<str:wallet_id>/set-default/', views.WalletSetDefaultView.as_view()),

    # ACCOUNT LOOKUP (by phone, for Send) + RECEIVE QR CODE
    path('accounts/lookup/<str:phone>/', views.AccountLookupView.as_view()),
    path('accounts/receive-qr/', views.ReceiveQRCodeView.as_view()),

    # SEND / EXCHANGE
    path('send/', views.SendView.as_view()),
    path('exchange/', views.ExchangeView.as_view()),

    # MONEY REQUEST (reverse of Send)
    path('requests/', views.MoneyRequestListCreateView.as_view()),
    path('requests/<str:pk>/accept/', views.MoneyRequestAcceptView.as_view()),
    path('requests/<str:pk>/decline/', views.MoneyRequestDeclineView.as_view()),

    # SCHEDULED / RECURRING PAYMENTS
    path('scheduled-payments/', views.ScheduledPaymentListCreateView.as_view()),
    path(
        'scheduled-payments/<str:schedule_id>/cancel/',
        views.ScheduledPaymentCancelView.as_view(),
    ),
    path(
        'scheduled-payments/<str:schedule_id>/pause-toggle/',
        views.ScheduledPaymentPauseToggleView.as_view(),
    ),

    # TRANSACTIONS
    path('transactions/', views.TransactionListView.as_view()),
    path('transactions/export/', views.TransactionExportCSVView.as_view()),

    # DASHBOARD
    path('dashboard/summary/', views.DashboardSummaryView.as_view()),

    # LOGIN SESSIONS
    path('sessions/', views.LoginSessionListView.as_view()),

    # NOTIFICATIONS
    path('notifications/', views.NotificationListView.as_view()),
    path(
        'notifications/<int:pk>/read/',
        views.NotificationMarkReadView.as_view(),
    ),

    # ACCOUNT TYPE / DEACTIVATION
    path('profile/account-type/', views.AccountTypeUpdateView.as_view()),
    path('profile/deactivate/', views.DeactivateAccountView.as_view()),

    # GROUP PAYMENTS (SPLIT BILL)
    path('group-payments/', views.GroupPaymentListCreateView.as_view()),
    path(
        'group-payments/<str:group_payment_id>/pay/',
        views.GroupPaymentPayShareView.as_view(),
    ),

    # SAVINGS GOALS
    path('savings-goals/', views.SavingsGoalListCreateView.as_view()),
    path('savings-goals/<str:goal_id>/top-up/', views.SavingsGoalTopUpView.as_view()),
    path('savings-goals/<str:goal_id>/deactivate/', views.SavingsGoalDeactivateView.as_view()),

    # PRICE ALERTS
    path('price-alerts/', views.PriceAlertListCreateView.as_view()),
    path('price-alerts/<str:pk>/', views.PriceAlertDeleteView.as_view()),

    # MERCHANT PAYMENT LINKS
    path('payment-links/', views.PaymentLinkListCreateView.as_view()),
    path('payment-links/<str:link_id>/pay/', views.PaymentLinkPublicView.as_view()),

    # PDF EXPORT
    path('transactions/export-pdf/', views.TransactionExportPDFView.as_view()),

    # ADMIN — API RATE LIMIT STATUS
    path('admin/rate-limit-status/', views.AdminRateLimitStatusView.as_view()),
]
