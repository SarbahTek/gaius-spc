from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """Allows access only to users whose role is 'admin'."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'role', None) == 'admin'
        )
