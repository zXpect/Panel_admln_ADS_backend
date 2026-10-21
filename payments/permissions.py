from rest_framework.permissions import BasePermission

from .authentication import FirebaseUser


class IsAppUser(BasePermission):
    """Usuario de la app móvil (ID token de Firebase)."""
    message = 'Requiere una sesión de la app'

    def has_permission(self, request, view):
        return isinstance(request.user, FirebaseUser)


class IsPanelUser(BasePermission):
    """Usuario del panel admin (JWT de simplejwt / sesión de Django)."""
    message = 'Requiere una sesión del panel administrativo'

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and not isinstance(user, FirebaseUser))


class IsAppOrPanelUser(BasePermission):
    def has_permission(self, request, view):
        return IsAppUser().has_permission(request, view) or IsPanelUser().has_permission(request, view)
