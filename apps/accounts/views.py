import logging

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart.services import merge_guest_cart
from apps.core import audit

from . import emails
from .models import Address, User
from .serializers import (
    AddressSerializer,
    EmailSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    RegisterSerializer,
    TokenSerializer,
    UserSerializer,
)
from .tokens import email_verification_token, password_reset_token, user_from_uid

logger = logging.getLogger("eunice.auth")


class InvalidCredentials(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Email or password is incorrect."
    default_code = "invalid_credentials"


class EmailNotVerified(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Confirm your email before signing in. We can send the link again."
    default_code = "email_not_verified"


@method_decorator(csrf_protect, name="dispatch")
class PublicAuthView(APIView):
    """Signed-out endpoints: still CSRF-protected and tightly rate-limited."""

    permission_classes = [AllowAny]
    serializer_class = None

    def data(self, request) -> dict:
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.serializer = serializer
        return serializer.validated_data


class CsrfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request) -> Response:
        return Response({"csrfToken": get_token(request)})


class RegisterView(PublicAuthView):
    serializer_class = RegisterSerializer
    throttle_scope = "auth_register"

    def post(self, request) -> Response:
        self.data(request)
        user = self.serializer.save()
        emails.send_verification_email(user)
        logger.info("register user_id=%s", user.pk)
        return Response(
            {"message": "Account created. Check your email for a link to confirm it."}, status=status.HTTP_201_CREATED
        )


class VerifyEmailView(PublicAuthView):
    serializer_class = TokenSerializer
    throttle_scope = "auth_login"

    def post(self, request) -> Response:
        data = self.data(request)
        user = user_from_uid(data["uid"])
        if user is None or not email_verification_token.check_token(user, data["token"]):
            raise ValidationError("This confirmation link is invalid or has expired. Request a new one.")
        if not user.email_verified:
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at"])
        return Response({"message": "Email confirmed. You can sign in now."})


class ResendVerificationView(PublicAuthView):
    serializer_class = EmailSerializer
    throttle_scope = "auth_email"

    def post(self, request) -> Response:
        email = self.data(request)["email"].lower()
        user = User.objects.filter(email=email, is_active=True, email_verified_at__isnull=True).first()
        if user:
            emails.send_verification_email(user)
        # Same answer either way so this cannot be used to discover accounts.
        return Response({"message": "If that email needs confirming, a new link is on its way."})


class LoginView(PublicAuthView):
    serializer_class = LoginSerializer
    throttle_scope = "auth_login"

    def post(self, request) -> Response:
        data = self.data(request)
        user = authenticate(request, username=data["email"].lower(), password=data["password"])
        if user is None:
            logger.warning("login_failed ip=%s", audit.client_ip(request))
            raise InvalidCredentials()
        if not user.email_verified:
            raise EmailNotVerified()
        login(request, user)  # rotates the session key
        merge_guest_cart(request, user)
        logger.info("login user_id=%s", user.pk)
        return Response({"user": UserSerializer(user).data})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        return Response(UserSerializer(request.user).data)

    def patch(self, request) -> Response:
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth_login"

    def post(self, request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            raise ValidationError({"current_password": ["Current password is incorrect."]})
        serializer.check_new_password(serializer.validated_data["new_password"], user)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)  # this device stays signed in; all others are signed out
        audit.record("account.password_changed", request=request, obj=user)
        return Response({"message": "Password changed."})


class PasswordResetRequestView(PublicAuthView):
    serializer_class = EmailSerializer
    throttle_scope = "auth_email"

    def post(self, request) -> Response:
        email = self.data(request)["email"].lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if user:
            emails.send_password_reset_email(user)
        return Response({"message": "If an account uses that email, a reset link is on its way."})


class PasswordResetConfirmView(PublicAuthView):
    serializer_class = PasswordResetConfirmSerializer
    throttle_scope = "auth_login"

    def post(self, request) -> Response:
        data = self.data(request)
        user = user_from_uid(data["uid"])
        if user is None or not user.is_active or not password_reset_token.check_token(user, data["token"]):
            raise ValidationError("This reset link is invalid or has expired. Request a new one.")
        self.serializer.check_new_password(data["new_password"], user)
        user.set_password(data["new_password"])
        # Receiving the reset email proves ownership of the address.
        user.email_verified_at = user.email_verified_at or timezone.now()
        user.save(update_fields=["password", "email_verified_at"])
        audit.record("account.password_reset", request=request, actor=user, obj=user)
        return Response({"message": "Password changed. You can sign in now."})


class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Address.objects.none()
        return Address.objects.filter(user=self.request.user)  # never another customer's rows

    def perform_create(self, serializer) -> None:
        serializer.save(user=self.request.user)
