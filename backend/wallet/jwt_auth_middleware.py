"""
Authenticates WebSocket connections using the same JWT access token
the REST API already uses — passed as a query string param since
browsers can't set custom headers on a WebSocket handshake:

    ws://host/ws/notifications/?token=<access token>

Wrap AuthMiddlewareStack (Channels' own session/cookie auth) with
this so `self.scope["user"]` is populated the same way DRF's
JWTAuthentication populates `request.user` on the HTTP side.
"""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError


@database_sync_to_async
def get_user_from_token(token):

    from wallet import db as rawsql
    from wallet.models import User

    try:
        validated = AccessToken(token)
        row = rawsql.get_row(User, 'id', validated["user_id"])
        if row is None:
            return AnonymousUser()
        return rawsql.hydrate(User, row)
    except (TokenError, KeyError):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):

    async def __call__(self, scope, receive, send):

        query_string = scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        token = params.get("token", [None])[0]

        scope["user"] = (
            await get_user_from_token(token) if token else AnonymousUser()
        )

        return await super().__call__(scope, receive, send)
