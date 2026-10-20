import hmac
import time

import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ApiClient:
    """Caller authenticated with a Kutuma API key, not a Django user."""

    is_authenticated = True

    def __str__(self):
        return "kutuma-api"


def issue_access_token() -> str:
    now = int(time.time())
    lifetime = settings.JWT_ACCESS_MINUTES * 60
    payload = {"sub": "kutuma-frontend", "iat": now, "exp": now + lifetime}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def issue_staff_token(username: str) -> str:
    now = int(time.time())
    lifetime = settings.JWT_ACCESS_MINUTES * 60
    payload = {"sub": username, "role": "staff", "iat": now, "exp": now + lifetime}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])


def api_key_matches(presented: str) -> bool:
    expected = settings.KUTUMA_API_KEY
    if not expected or not presented:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


class JWTAuthentication(BaseAuthentication):
    """Require Authorization: Bearer <jwt> on every API request."""

    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise AuthenticationFailed("Authentication credentials were not provided.")
        try:
            decode_token(token.strip())
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed("Invalid token.") from exc
        return (ApiClient(), None)


class StaffClient:
    """Django admin signed in for Ask AI."""

    is_authenticated = True

    def __init__(self, username: str):
        self.username = username

    def __str__(self):
        return self.username


class StaffJWTAuthentication(BaseAuthentication):
    """Accept only a JWT issued for an admin, not the desk API-key token."""

    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise AuthenticationFailed("Admin login is required.")
        try:
            payload = decode_token(token.strip())
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed("Admin login is required.") from exc
        if payload.get("role") != "staff" or not payload.get("sub"):
            raise AuthenticationFailed("Admin login is required.")
        return (StaffClient(str(payload["sub"])), None)
