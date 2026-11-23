"""Token issuing / rotation shared by traveler (mobile + web) and staff auth."""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User


def obtain(email, password):
    """Return (user, access, refresh) or raise AuthenticationFailed."""
    s = TokenObtainPairSerializer(data={"email": (email or "").lower(), "password": password})
    s.is_valid(raise_exception=True)
    return s.user, s.validated_data["access"], s.validated_data["refresh"]


def rotate(raw_refresh):
    """Return (access, new_refresh); rejects blacklisted tokens and deleted users."""
    try:
        token = RefreshToken(raw_refresh)
    except TokenError:
        raise AuthenticationFailed("Session expired.")
    if not User.objects.filter(pk=token.get("user_id")).exists():
        raise AuthenticationFailed("Session expired.")
    s = TokenRefreshSerializer(data={"refresh": raw_refresh})
    s.is_valid(raise_exception=True)
    return s.validated_data["access"], s.validated_data["refresh"]


def revoke(raw_refresh):
    try:
        RefreshToken(raw_refresh).blacklist()
    except TokenError:
        pass  # already invalid: logout stays idempotent


def user_from_refresh(raw_refresh):
    return User.objects.filter(pk=RefreshToken(raw_refresh, verify=False).get("user_id")).first()
