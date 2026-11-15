from django.db.models import *
from django.db import transaction
from app_movil_mantenimiento_api.serializers import UserSerializer
from app_movil_mantenimiento_api.serializers import *
from app_movil_mantenimiento_api.models import *
from rest_framework import permissions
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import BasePermission
from django.contrib.auth.models import Group
import json 
from django.shortcuts import get_object_or_404

class IsAdministrator(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.groups.filter(name="administrador").exists()

class TrabajadoresAll(generics.CreateAPIView):
    #Esta función es esencial para todo donde se requiera autorización de inicio de sesión (token)
    permission_classes = (permissions.IsAuthenticated,)
    # Invocamos la petición GET para obtener todos los alumnos
    def get(self, request, *args, **kwargs):
        trabajadores = Trabajadores.objects.filter().order_by("id")
        lista = TrabajadoresSerializer(trabajadores, many=True).data
        return Response(lista, 200)
    
class TrabajadoresView(generics.CreateAPIView):
    def get_permissions(self):
        if self.request.method in ("GET", "PUT", "DELETE"):
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get(self, request, *args, **kwargs):
        trabajador = get_object_or_404(Trabajadores, id = request.GET.get("id"))
        trabajador = TrabajadoresSerializer(trabajador, many=False).data
        return Response(trabajador, 200)
    
    @transaction.atomic
    def post(self, request, *args, **kwargs):

        user = UserSerializer(data=request.data)

        if user.is_valid():
            #Grab user data
            role = request.data['rol']
            first_name = request.data['first_name']
            last_name = request.data['last_name']
            email = request.data['email']
            password = request.data['password']

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
                                            id_trabajador=request.data["id_trabajador"],
                                            telefono=request.data["telefono"],
                                            fecha_nacimiento=request.data["fecha_nacimiento"],
                                            departamento=request.data["departamento"],
                                            biblioteca=request.data["biblioteca"],
                                            edad=request.data["edad"],                                                   
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
                            f"El usuario {first_name} {last_name} está pendiente "
                            "de validación."
                        ),
                    )
                    for administrador in administradores
                ]
            )

            return Response({"trabajador_created_id": trabajadores.id }, 201)

        return Response(user.errors, status=status.HTTP_400_BAD_REQUEST)
    @transaction.atomic
    def put(self, request, *args, **kwargs):
        trabajador = get_object_or_404(Trabajadores, id=request.data["id"])
        is_administrator = request.user.groups.filter(name="administrador").exists()
        if not is_administrator and (
            trabajador.user_id != request.user.id or not trabajador.is_validated
        ):
            return Response({"detail": "El perfil aún no está validado"}, status=status.HTTP_403_FORBIDDEN)

        trabajador.id_trabajador = request.data["id_trabajador"]
        trabajador.telefono = request.data["telefono"]
        trabajador.fecha_nacimiento = request.data["fecha_nacimiento"]
        trabajador.biblioteca = request.data["biblioteca"]
        trabajador.edad = request.data["edad"]
        trabajador.departamento = request.data["departamento"]
        trabajador.save()
        user = trabajador.user
        user.first_name = request.data["first_name"]
        user.last_name = request.data["last_name"]
        user.save()
        
        return Response({"message": "Trabajador actualizado correctamente", "trabajador": TrabajadoresSerializer(trabajador).data}, 200)
    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        trabajador = get_object_or_404(Trabajadores, id=request.GET.get("id"))
        is_administrator = request.user.groups.filter(name="administrador").exists()
        if not is_administrator and (
            trabajador.user_id != request.user.id or not trabajador.is_validated
        ):
            return Response({"detail": "El perfil aún no está validado"}, status=status.HTTP_403_FORBIDDEN)

        try:
            trabajador.user.delete()
            return Response({"details":"Trabajador eliminado"},200)
        except Exception:
            return Response({"details":"Algo pasó al eliminar"},400)


class ValidarTrabajadorView(APIView):
    permission_classes = (IsAdministrator,)

    @transaction.atomic
    def put(self, request, *args, **kwargs):
        trabajador = get_object_or_404(Trabajadores, id=request.data["id"])
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
