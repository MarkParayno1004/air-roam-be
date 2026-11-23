import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

ROLE_ADMIN = "admin"
ROLE_MARKETING = "marketing"
ROLE_CHOICES = [(ROLE_ADMIN, "Admin"), (ROLE_MARKETING, "Marketing")]


class UserManager(BaseUserManager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def create_user(self, email, password=None, **fields):
        user = self.model(email=email.strip().lower(), **fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **fields):
        fields.setdefault("is_superuser", True)
        fields.setdefault("permissions", [ROLE_ADMIN])
        return self.create_user(email, password, **fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True)
    contact_no = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    pin_point_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pin_point_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pin_point_label = models.CharField(max_length=255, null=True, blank=True)
    permissions = ArrayField(models.CharField(max_length=20, choices=ROLE_CHOICES), default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()
    all_objects = models.Manager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_ci_unique")]

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.deleted_at is None

    @property
    def is_staff(self):  # Django admin access: developers (superusers) only
        return self.is_superuser

    @property
    def is_staff_member(self):
        return bool(self.permissions)

    def has_role(self, role):
        return role in (self.permissions or [])

    @property
    def effective_address(self) -> str:
        if self.pin_point_lat is not None and self.pin_point_lng is not None:
            return self.pin_point_label or f"{self.pin_point_lat},{self.pin_point_lng}"
        return self.address

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    def __str__(self):
        return self.email
