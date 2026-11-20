from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from apps.common.models import SoftDeleteModel, TimeStampedModel, UUIDModel


class UserManager(BaseUserManager):
    def create_user(self, username: str, password: str | None = None, **extra):
        if not username:
            raise ValueError("Username is required")
        user = self.model(username=username.lower().strip(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        return self.create_user(username, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, UUIDModel, TimeStampedModel, SoftDeleteModel):
    username = models.CharField(max_length=64, unique=True)
    email = models.EmailField(blank=True, default="")
    first_name = models.CharField(max_length=128, blank=True, default="")
    last_name = models.CharField(max_length=128, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    totp_enabled = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return self.username

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.username


class Permission(UUIDModel, TimeStampedModel):
    """module.action permission codes, e.g. accounts.user.create"""

    code = models.CharField(max_length=128, unique=True)
    module = models.CharField(max_length=64, db_index=True)
    action = models.CharField(max_length=64)
    description = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["module", "action"]

    def __str__(self) -> str:
        return self.code


class Role(UUIDModel, TimeStampedModel):
    """
    facility=null means a system template role.
    Seed copies templates per facility.
    """

    facility = models.ForeignKey(
        "organizations.Facility",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="roles",
    )
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, default="")
    is_system = models.BooleanField(default=False)
    max_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    max_discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    own_collection_only = models.BooleanField(default=False)
    permissions = models.ManyToManyField(
        Permission,
        through="RolePermission",
        related_name="roles",
        blank=True,
    )
    screens = models.ManyToManyField(
        "Screen",
        through="RoleScreen",
        related_name="roles",
        blank=True,
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "code"],
                name="uniq_role_facility_code",
            )
        ]

    def __str__(self) -> str:
        scope = self.facility.code if self.facility_id else "SYSTEM"
        return f"{scope}:{self.code}"


class RolePermission(UUIDModel, TimeStampedModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role", "permission"],
                name="uniq_role_permission",
            )
        ]


class Screen(UUIDModel, TimeStampedModel):
    """UI routes that can be granted per role (replaces legacy User Screen Settings)."""

    code = models.CharField(max_length=64, unique=True)
    module = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=128)
    route = models.CharField(max_length=255)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["module", "sort_order", "name"]

    def __str__(self) -> str:
        return self.code


class RoleScreen(UUIDModel, TimeStampedModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["role", "screen"], name="uniq_role_screen")
        ]
        ordering = ["sort_order"]


class Membership(UUIDModel, TimeStampedModel, SoftDeleteModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    facility = models.ForeignKey(
        "organizations.Facility",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "facility", "role"],
                name="uniq_membership_user_facility_role",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user.username}@{self.facility.code}:{self.role.code}"
