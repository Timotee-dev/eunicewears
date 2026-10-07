"""Role checks enforced by the backend. Hiding a button is never the control."""
from rest_framework.permissions import BasePermission

ROLE_RANK = {"customer": 0, "staff": 1, "admin": 2, "super_admin": 3}


def has_role(user, minimum: str) -> bool:
    return bool(
        user and user.is_authenticated and user.is_active and ROLE_RANK.get(user.role, 0) >= ROLE_RANK[minimum]
    )


class IsStaff(BasePermission):
    def has_permission(self, request, view) -> bool:
        return has_role(request.user, "staff")


class IsAdmin(BasePermission):
    def has_permission(self, request, view) -> bool:
        return has_role(request.user, "admin")


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view) -> bool:
        return has_role(request.user, "super_admin")
