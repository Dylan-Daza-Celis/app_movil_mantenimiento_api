from rest_framework import generics, permissions
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.response import Response
from django.conf import settings
from django.utils import timezone

from app_movil_mantenimiento_api.models import Administradores, Trabajadores
from app_movil_mantenimiento_api.permissions import is_administrator
from app_movil_mantenimiento_api.serializers import AdminSerializer, TrabajadoresSerializer
from app_movil_mantenimiento_api.throttles import LoginThrottle


def session_data(user):
    if is_administrator(user):
        profile = Administradores.objects.filter(user=user).first()
        return {**AdminSerializer(profile).data, "rol": "administrador"} if profile else None
    if user.groups.filter(name="trabajador").exists():
        profile = Trabajadores.objects.filter(user=user).first()
        return {**TrabajadoresSerializer(profile).data, "rol": "trabajador"} if profile else None
    return None


class CustomAuthToken(ObtainAuthToken):
    throttle_classes = (LoginThrottle,)

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        data = session_data(user)
        if data is None:
            return Response({"detail": "La cuenta no tiene un perfil habilitado."}, status=403)
        token, _ = Token.objects.get_or_create(user=user)
        if (timezone.now() - token.created).total_seconds() >= settings.AUTH_TOKEN_MAX_AGE_SECONDS:
            Token.objects.filter(pk=token.pk).delete()
            token, _ = Token.objects.get_or_create(user=user)
        return Response({**data, "token": token.key})


class MeView(generics.GenericAPIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        data = session_data(request.user)
        if data is None:
            return Response({"detail": "La cuenta no tiene un perfil habilitado."}, status=403)
        return Response(data)


class Logout(generics.GenericAPIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"logout": True})

    # Compatibility with previously deployed clients.
    def get(self, request):
        return self.post(request)
