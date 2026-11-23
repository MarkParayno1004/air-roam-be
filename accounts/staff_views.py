from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from accounts.auth import STAFF_COOKIE
from accounts.models import User
from accounts.permissions import IsAdminRole
from accounts.serializers import USER_FIELDS
from accounts.views import CookieLoginView, CookieLogoutView, CookieRefreshView


class StaffLoginView(CookieLoginView):
    cookie = STAFF_COOKIE

    def check_user(self, user):
        if not user.is_staff_member:
            raise PermissionDenied("This account has no staff access.")


class StaffRefreshView(CookieRefreshView):
    cookie = STAFF_COOKIE


class StaffLogoutView(CookieLogoutView):
    cookie = STAFF_COOKIE


class StaffUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = USER_FIELDS + ["password", "created_at"]
        read_only_fields = ["id", "effective_address", "created_at"]

    def validate_email(self, value):
        value = value.lower()
        qs = User.all_objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        if not self.instance and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Required."})
        if attrs.get("password"):
            try:
                validate_password(attrs["password"])
            except DjangoValidationError as e:
                raise serializers.ValidationError({"password": e.messages})
        return attrs

    def create(self, data):
        return User.objects.create_user(data.pop("email"), data.pop("password"), **data)

    def update(self, instance, data):
        password = data.pop("password", None)
        if password:
            instance.set_password(password)
        return super().update(instance, data)


class StaffUserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminRole]
    serializer_class = StaffUserSerializer

    def get_queryset(self):
        qs = User.objects.order_by("email")
        q = self.request.query_params.get("search")
        if q:
            qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
        return qs

    def destroy(self, request, *args, **kwargs):
        self.get_object().soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
