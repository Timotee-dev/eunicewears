from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Address, User


class UserSerializer(serializers.ModelSerializer):
    email_verified = serializers.BooleanField(read_only=True)
    marketing_opt_in = serializers.BooleanField(source="profile.marketing_opt_in", required=False)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone", "role", "email_verified", "marketing_opt_in", "date_joined"]
        read_only_fields = ["id", "email", "role", "date_joined"]

    def update(self, instance: User, validated_data: dict) -> User:
        profile_data = validated_data.pop("profile", None)
        instance = super().update(instance, validated_data)
        if profile_data is not None:
            instance.profile.marketing_opt_in = profile_data["marketing_opt_in"]
            instance.profile.save(update_fields=["marketing_opt_in", "updated_at"])
        return instance


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    marketing_opt_in = serializers.BooleanField(required=False, default=False)

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists. Sign in instead.")
        return value

    def validate(self, attrs: dict) -> dict:
        candidate = User(email=attrs["email"], first_name=attrs["first_name"], last_name=attrs["last_name"])
        try:
            validate_password(attrs["password"], candidate)
        except Exception as exc:  # django ValidationError
            raise serializers.ValidationError({"password": list(getattr(exc, "messages", [str(exc)]))})
        return attrs

    def create(self, validated_data: dict) -> User:
        opt_in = validated_data.pop("marketing_opt_in", False)
        user = User.objects.create_user(**validated_data)  # role is always customer here
        if opt_in:
            user.profile.marketing_opt_in = True
            user.profile.save(update_fields=["marketing_opt_in", "updated_at"])
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class TokenSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


class NewPasswordMixin:
    def check_new_password(self, password: str, user: User) -> None:
        try:
            validate_password(password, user)
        except Exception as exc:
            raise serializers.ValidationError({"new_password": list(getattr(exc, "messages", [str(exc)]))})


class PasswordResetConfirmSerializer(NewPasswordMixin, TokenSerializer):
    new_password = serializers.CharField(trim_whitespace=False)


class PasswordChangeSerializer(NewPasswordMixin, serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        exclude = ["user"]
        read_only_fields = ["id", "created_at", "updated_at"]
