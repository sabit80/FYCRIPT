"""
Wraps SimpleJWT's authentication with a raw-SQL check against
wallet_blacklisted_token so that a token LogoutView has blacklisted is
rejected immediately instead of staying valid until its natural
expiry. This is what makes "Logout" actually invalidate the session
(see LogoutView in views.py) instead of only clearing the token on
the client, which the CSE216 60% guideline calls out by name as a
common mistake.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from . import db as rawsql


def is_blacklisted(jti):
    return bool(rawsql.scalar(
        "SELECT 1 FROM wallet_blacklisted_token WHERE jti = %s LIMIT 1", [jti],
    ))


class BlacklistCheckingJWTAuthentication(JWTAuthentication):

    def get_validated_token(self, raw_token):
        validated_token = super().get_validated_token(raw_token)

        jti = validated_token.get('jti')
        if jti and is_blacklisted(jti):
            raise AuthenticationFailed(
                "This token has been logged out.", code='token_blacklisted',
            )

        return validated_token
