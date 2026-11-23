from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import User

USER_FIELDS = [
    "id", "first_name", "last_name", "email", "contact_no", "address",
    "pin_point_lat", "pin_point_lng", "pin_point_label", "effective_address", "permissions",
]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = USER_FIELDS
        read_only_fields = ["id", "email", "permissions", "effective_address"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "contact_no", "address", "password"]
        extra_kwargs = {"first_name": {"required": True}, "last_name": {"required": True}}

    def validate_email(self, value):
        if User.all_objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        try:
            validate_password(attrs["password"], User(**{k: v for k, v in attrs.items() if k != "password"}))
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": e.messages})
        return attrs

    def create(self, data):
        return User.objects.create_user(data.pop("email"), data.pop("password"), **data)
