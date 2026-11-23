from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts import tokens
from accounts.auth import WEB_COOKIE, clear_refresh_cookie, enforce_csrf, set_refresh_cookie
from accounts.serializers import RegisterSerializer, UserSerializer


LOGIN_IN = inline_serializer("LoginInput", {"email": serializers.EmailField(), "password": serializers.CharField()})
TOKEN_PAIR = inline_serializer("TokenPair", {"access": serializers.CharField(), "refresh": serializers.CharField()})
REFRESH_IN = inline_serializer("RefreshInput", {"refresh": serializers.CharField()})
ACCESS_OUT = inline_serializer("AccessToken", {"access": serializers.CharField()})
SESSION_OUT = inline_serializer("Session", {"access": serializers.CharField(), "user": UserSerializer()})
CSRF_OUT = inline_serializer("CsrfToken", {"csrfToken": serializers.CharField()})


class PublicView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_authenticate_header(self, request):
        return 'Bearer realm="api"'  # keeps failed logins/refreshes at 401, not 403


class AuthThrottled(PublicView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class CsrfView(PublicView):
    @extend_schema(responses=CSRF_OUT)
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RegisterView(AuthThrottled):
    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer})
    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(UserSerializer(s.save()).data, status=status.HTTP_201_CREATED)


# --- mobile: tokens in the body ---------------------------------------------
class LoginView(AuthThrottled):
    @extend_schema(request=LOGIN_IN, responses=TOKEN_PAIR)
    def post(self, request):
        _, access, refresh = tokens.obtain(request.data.get("email"), request.data.get("password"))
        return Response({"access": access, "refresh": refresh})


class RefreshView(PublicView):
    @extend_schema(request=REFRESH_IN, responses=TOKEN_PAIR)
    def post(self, request):
        access, refresh = tokens.rotate(request.data.get("refresh", ""))
        return Response({"access": access, "refresh": refresh})


class LogoutView(PublicView):
    @extend_schema(request=REFRESH_IN, responses={204: None})
    def post(self, request):
        tokens.revoke(request.data.get("refresh", ""))
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- browser: refresh token in an HttpOnly cookie -----------------------------
class CookieLoginView(AuthThrottled):
    cookie = WEB_COOKIE

    def check_user(self, user):
        """Hook for staff login (role check)."""

    @extend_schema(request=LOGIN_IN, responses=SESSION_OUT)
    def post(self, request):
        user, access, refresh = tokens.obtain(request.data.get("email"), request.data.get("password"))
        self.check_user(user)
        response = Response({"access": access, "user": UserSerializer(user).data})
        set_refresh_cookie(response, *self.cookie, refresh)
        return response


class CookieRefreshView(PublicView):
    cookie = WEB_COOKIE

    @extend_schema(request=None, responses=ACCESS_OUT)
    def post(self, request):
        enforce_csrf(request)
        access, refresh = tokens.rotate(request.COOKIES.get(self.cookie[0], ""))
        response = Response({"access": access})
        set_refresh_cookie(response, *self.cookie, refresh)
        return response


class CookieLogoutView(PublicView):
    cookie = WEB_COOKIE

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        enforce_csrf(request)
        tokens.revoke(request.COOKIES.get(self.cookie[0], ""))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response, *self.cookie)
        return response


@extend_schema(request=UserSerializer, responses={200: UserSerializer, 204: None})
class MeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        s = UserSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

    def delete(self, request):
        request.user.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
