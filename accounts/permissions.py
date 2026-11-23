from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.models import ROLE_ADMIN, ROLE_MARKETING


def _user(request):
    u = request.user
    return u if u and u.is_authenticated else None


class IsStaff(BasePermission):
    def has_permission(self, request, view):
        u = _user(request)
        return bool(u and u.is_staff_member)


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        u = _user(request)
        return bool(u and u.has_role(ROLE_ADMIN))


class IsMarketingOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = _user(request)
        return bool(u and (u.has_role(ROLE_ADMIN) or u.has_role(ROLE_MARKETING)))


class AdminWriteOtherwiseStaffRead(BasePermission):
    """Any staff member may read; only admins may change."""

    def has_permission(self, request, view):
        u = _user(request)
        if not (u and u.is_staff_member):
            return False
        return request.method in SAFE_METHODS or u.has_role(ROLE_ADMIN)
