from django.db.models.deletion import ProtectedError
from django.utils import timezone
from app_movil_mantenimiento_api.validation import positive_id
from app_movil_mantenimiento_api.profile_validation import profile_input, registration_conflict
from app_movil_mantenimiento_api.throttles import RegistrationThrottle
from django.db import transaction
from app_movil_mantenimiento_api.serializers import UserSerializer
from app_movil_mantenimiento_api.serializers import AdminSerializer, TrabajadoresSerializer
from app_movil_mantenimiento_api.models import Administradores, Trabajadores, Notificacion
from django.contrib.auth.models import User
from rest_framework import permissions
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404

from app_movil_mantenimiento_api.permissions import IsAdministrator

class TrabajadoresAll(generics.GenericAPIView):
    #Esta función es esencial para todo donde se requiera autorización de inicio de sesión (token)
    permission_classes = (IsAdministrator,)
    # Invocamos la petición GET para obtener todos los alumnos
    def get(self, request, *args, **kwargs):
        trabajadores = Trabajadores.objects.select_related("user").order_by("id")
        lista = TrabajadoresSerializer(trabajadores, many=True).data
        return Response(lista, 200)

class TrabajadoresView(generics.GenericAPIView):
    throttle_classes = (RegistrationThrottle,)
    def get_permissions(self):
        if self.request.method in ("GET", "PUT", "DELETE"):
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get(self, request, *args, **kwargs):
        trabajador = get_object_or_404(Trabajadores, id = positive_id(request.GET.get("id")))
        if not request.user.groups.filter(name="administrador").exists() and trabajador.user_id != request.user.id:
            return Response({"detail": "No tienes permiso para consultar este perfil."}, status=403)
        trabajador = TrabajadoresSerializer(trabajador, many=False).data
        return Response(trabajador, 200)

    @registration_conflict
    @transaction.atomic
    def post(self, request, *args, **kwargs):

        if request.data.get("rol", "trabajador") != "trabajador":
            return Response({"rol": ["El registro solo permite trabajadores."]}, status=400)
        validated = profile_input(request, "trabajador", creating=True)
        user = UserSerializer(data=validated)

        if user.is_valid():
            #Grab user data
            role = "trabajador"
            first_name = validated['first_name']
            last_name = validated['last_name']
            email = validated['email']
            password = validated['password']

            existing_user = User.objects.filter(email=email).first()

            if existing_user:
                return Response({"message":"Username "+email+", is already taken"},400)

            user = User.objects.create( username = email,
                                        email = email,
                                        first_name = first_name,
                                        last_name = last_name,
                                        is_active = 1)


            user.save()

            user.set_password(password)
            user.save()

            group, created = Group.objects.get_or_create(name=role)
            group.user_set.add(user)
            user.save()

            trabajadores = Trabajadores.objects.create(user=user,
                                            id_trabajador=validated["id_trabajador"],
                                            telefono=validated["telefono"],
                                            fecha_nacimiento=validated["fecha_nacimiento"],
                                            departamento=validated["departamento"],
                                            biblioteca=validated["biblioteca"],
                                            edad=validated["edad"],
                                            )

            trabajadores.save()

            administradores = User.objects.filter(
                groups__name="administrador"
            ).distinct()
            Notificacion.objects.bulk_create(
                [
                    Notificacion(
                        destinatario=administrador,
                        tipo=Notificacion.TIPO_USUARIO_PENDIENTE,
                        mensaje=(
                            f"El usuario {first_name} {last_name} está pendiente de validación."[:255]
                        ),
                    )
                    for administrador in administradores
                ]
            )

            return Response({"trabajador_created_id": trabajadores.id }, 201)

        return Response(user.errors, status=status.HTTP_400_BAD_REQUEST)
    @transaction.atomic
    def put(self, request, *args, **kwargs):
        validated = profile_input(request, "trabajador")
        trabajador = get_object_or_404(Trabajadores, id=positive_id(request.data.get("id")))
        is_administrator = request.user.groups.filter(name="administrador").exists()
        if not is_administrator and (
            trabajador.user_id != request.user.id or not trabajador.is_validated
        ):
            return Response({"detail": "El perfil aún no está validado"}, status=status.HTTP_403_FORBIDDEN)

        trabajador.id_trabajador = validated["id_trabajador"]
        trabajador.telefono = validated["telefono"]
        trabajador.fecha_nacimiento = validated["fecha_nacimiento"]
        trabajador.biblioteca = validated["biblioteca"]
        trabajador.edad = validated["edad"]
        trabajador.departamento = validated["departamento"]
        trabajador.update = timezone.now()
        trabajador.save()
        user = trabajador.user
        user.first_name = validated["first_name"]
        user.last_name = validated["last_name"]
        user.save()

        return Response({"message": "Trabajador actualizado correctamente", "trabajador": TrabajadoresSerializer(trabajador).data}, 200)
    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        trabajador = get_object_or_404(Trabajadores, id=positive_id(request.GET.get("id")))
        is_administrator = request.user.groups.filter(name="administrador").exists()
        if not is_administrator and (
            trabajador.user_id != request.user.id or not trabajador.is_validated
        ):
            return Response({"detail": "El perfil aún no está validado"}, status=status.HTTP_403_FORBIDDEN)

        try:
            trabajador.user.delete()
            return Response({"details":"Trabajador eliminado"},200)
        except ProtectedError:
            return Response({"details":"El usuario tiene tickets asociados y no puede eliminarse"},400)


class ValidarTrabajadorView(APIView):
    permission_classes = (IsAdministrator,)

    @transaction.atomic
    def put(self, request, *args, **kwargs):
        if not isinstance(request.data.get("is_validated"), bool):
            return Response({"is_validated": "Debe ser un booleano."}, status=400)
        trabajador = get_object_or_404(Trabajadores.objects.select_for_update(), id=positive_id(request.data.get("id")))
        estaba_validado = trabajador.is_validated
        trabajador.is_validated = request.data["is_validated"]
        trabajador.save(update_fields=["is_validated"])
        if trabajador.is_validated and not estaba_validado:
            Notificacion.objects.create(
                destinatario=trabajador.user,
                tipo=Notificacion.TIPO_USUARIO_VALIDADO,
                mensaje="Tu usuario ha sido validado. Ya puedes utilizar el sistema.",
            )
        return Response(
            {
                "message": "Estado de validación actualizado correctamente",
                "trabajador": TrabajadoresSerializer(trabajador).data,
            },
            status=status.HTTP_200_OK,
        )
