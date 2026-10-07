from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Role(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    STAFF = "staff", "Staff"
    ADMIN = "admin", "Admin"
    SUPER_ADMIN = "super_admin", "Super admin"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email: str, password: str | None, **extra) -> "User":
        if not email:
            raise ValueError("Email is required.")
        user = self.model(email=email.strip().lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra) -> "User":
        extra.setdefault("role", Role.CUSTOMER)
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra) -> "User":
        extra.update(role=Role.SUPER_ADMIN, is_superuser=True)
        extra.setdefault("email_verified_at", timezone.now())
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, editable=False)  # derived from role
    email_verified_at = models.DateTimeField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    def save(self, *args, **kwargs) -> None:
        self.email = self.email.strip().lower()
        self.is_staff = self.role != Role.CUSTOMER
        super().save(*args, **kwargs)

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self) -> str:
        return self.email


class CustomerProfile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    marketing_opt_in = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Profile<{self.user.email}>"


class Address(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=40, blank=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    phone = models.CharField(max_length=20)
    country = models.CharField(max_length=2, default="NG")
    state = models.CharField(max_length=80)
    city = models.CharField(max_length=80)
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    delivery_instructions = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(is_default=True), name="one_default_address_per_user"
            )
        ]

    def save(self, *args, **kwargs) -> None:
        with transaction.atomic():
            others = Address.objects.filter(user=self.user).exclude(pk=self.pk)
            if not others.exists():
                self.is_default = True
            if self.is_default:
                others.filter(is_default=True).update(is_default=False)
            super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.line1}, {self.city}"
