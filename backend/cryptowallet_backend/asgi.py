"""
ASGI config for cryptowallet_backend project.

Run with an ASGI server to get WebSocket support (plain `runserver`
only serves HTTP, so notifications-over-websocket needs this):

    pip install daphne
    daphne cryptowallet_backend.asgi:application

or:

    pip install uvicorn
    uvicorn cryptowallet_backend.asgi:application

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

import django
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cryptowallet_backend.settings')
django.setup()

from wallet.routing import websocket_urlpatterns  # noqa: E402  (needs django.setup() first)
from wallet.jwt_auth_middleware import JWTAuthMiddleware  # noqa: E402

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})

