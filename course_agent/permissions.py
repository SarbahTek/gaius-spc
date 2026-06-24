from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """Allows access only to users whose role is 'admin'."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'role', None) == 'admin'
        )


class IsInstructorOrAdmin(BasePermission):
    """Allows access to the studio: superusers, or admin/instructor roles."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_superuser or getattr(user, 'role', None) in ('admin', 'instructor'))
        )
