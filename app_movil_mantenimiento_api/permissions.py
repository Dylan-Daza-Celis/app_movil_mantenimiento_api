from rest_framework.permissions import BasePermission

from .models import Trabajadores


def is_administrator(user):
    return user.is_authenticated and user.groups.filter(name="administrador").exists()


class IsAdministrator(BasePermission):
    message = "Solo un administrador puede realizar esta operación."

    def has_permission(self, request, view):
        return is_administrator(request.user)


class IsValidatedUser(BasePermission):
    message = "Tu cuenta aún no está validada."

    def has_permission(self, request, view):
        return is_administrator(request.user) or (
            request.user.is_authenticated
            and request.user.groups.filter(name="trabajador").exists()
            and Trabajadores.objects.filter(user=request.user, is_validated=True).exists()
        )
