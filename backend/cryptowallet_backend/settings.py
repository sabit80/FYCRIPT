"""
Django settings for cryptowallet_backend project.
"""
 
import os
import dj_database_url
from datetime import timedelta
from pathlib import Path
 
BASE_DIR = Path(__file__).resolve().parent.parent
 
# Load a .env file if python-dotenv is installed (optional convenience —
# the app also works fine with real environment variables / a process
# manager / docker-compose env_file).
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass
 
 
def env(key, default=None):
    return os.environ.get(key, default)
 
 
def env_bool(key, default=False):
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')
 
 
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env(
    'DJANGO_SECRET_KEY',
    'django-insecure-lopq!!bqvmkcx@vq=)ve8kuqq5%(z9(t=-%=%tk-h&p6#ckaf2',
)
 
DEBUG = env_bool('DJANGO_DEBUG', True)
 
ALLOWED_HOSTS = [
    h.strip() for h in env('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')
    if h.strip()
]
 
 
# Application definition
 
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
 
    # third-party
    'channels',
    'rest_framework',
    'corsheaders',
    'drf_spectacular',
 
    # local
    'wallet',
]
 
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
 
# Use our own User model (email + phone instead of username)
AUTH_USER_MODEL = 'wallet.User'
 
ROOT_URLCONF = 'cryptowallet_backend.urls'
 
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
 
WSGI_APPLICATION = 'cryptowallet_backend.wsgi.application'
 
 
# =====================================================
# DATABASE — MySQL
#
# Configure via environment variables (see backend/.env.example).
# Defaults match a local `CREATE DATABASE cryptowallet_db` setup.
# =====================================================
 
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
 
 
# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
 
 
# Static files
STATIC_URL = 'static/'
 
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
 
 
# =====================================================
# DJANGO REST FRAMEWORK
# =====================================================
 
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Scoped throttles used by LoginView / TwoFactorLoginVerifyView
    # (brute-force protection) and SendView (basic API-level rate
    # limiting on top of the fraud-velocity check in views.py).
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'login': '10/min',
        'send': '30/min',
    },
}
 
SPECTACULAR_SETTINGS = {
    'TITLE': 'CryptoWallet API',
    'DESCRIPTION': (
        'Multi-currency (fiat + crypto) mobile-wallet backend — '
        'accounts, KYC, wallets, send, exchange, money requests.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}
 
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=6),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}
 
 
# =====================================================
# CORS
#
# The frontend is plain HTML/JS served from a different
# origin (e.g. VS Code Live Server on :5500, or just
# opened as a file). Add every origin you actually serve
# the frontend from, or set CORS_ALLOW_ALL_ORIGINS=true in .env
# while developing.
# =====================================================
 
# =====================================================
# FRONTEND ORIGIN
#
# Used to build absolute links that get emailed out (password reset)
# instead of a hardcoded host:port. Set this to wherever you actually
# serve frontend/ from.
# =====================================================
 
FRONTEND_URL = env('FRONTEND_URL', 'http://127.0.0.1:5500')
 
 
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in env(
        'CORS_ALLOWED_ORIGINS',
        'http://127.0.0.1:5500,http://localhost:5500,'
        'http://127.0.0.1:5501,http://localhost:5501,'
        'http://127.0.0.1:5503,http://localhost:5503',
    ).split(',') if o.strip()
]
 
CORS_ALLOW_ALL_ORIGINS = env_bool('CORS_ALLOW_ALL_ORIGINS', False)
 
 
# =====================================================
# CACHE
#
# Used to hold short-lived, non-critical state: the pending TOTP
# secret during 2FA setup (Enable2FASetupView) and the login_token
# issued mid-2FA-login (LoginView / TwoFactorLoginVerifyView). Local
# in-memory cache is fine for a single-process dev server; if you
# run multiple worker processes/machines in production, swap this
# for a shared backend (e.g. Redis) so one worker's cache.set() is
# visible to whichever worker handles the follow-up request.
# =====================================================
 
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
 
 
# =====================================================
# CHANNELS / WEBSOCKETS  (real-time notifications)
#
# ASGI_APPLICATION points at cryptowallet_backend.asgi.application,
# which routes ws:// connections through wallet/routing.py to
# NotificationConsumer. InMemoryChannelLayer is fine for a single
# `daphne`/`uvicorn` process in dev; for more than one worker
# process (or more than one machine) in production, switch to
# channels_redis so all workers share the same group membership:
#
#   CHANNEL_LAYERS = {
#       'default': {
#           'BACKEND': 'channels_redis.core.RedisChannelLayer',
#           'CONFIG': {"hosts": [('127.0.0.1', 6379)]},
#       }
#   }
#
# Run with an ASGI server instead of `runserver` to actually get
# WebSocket support: `pip install daphne` then
# `daphne cryptowallet_backend.asgi:application`, or `uvicorn
# cryptowallet_backend.asgi:application`.
# =====================================================
 
ASGI_APPLICATION = 'cryptowallet_backend.asgi.application'
 
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}
 
 
# Email
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'true') == 'true'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)