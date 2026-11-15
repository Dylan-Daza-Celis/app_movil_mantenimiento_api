from django.db.models import *
from django.db import transaction
from app_movil_mantenimiento_api.serializers import UserSerializer
from app_movil_mantenimiento_api.serializers import *
from app_movil_mantenimiento_api.models import *
from rest_framework import permissions
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response
from django.contrib.auth.models import Group
import json 
from django.shortcuts import get_object_or_404


class AdminAll(generics.CreateAPIView):
    #Esta función es esencial para todo donde se requiera autorización de inicio de sesión (token)
    permission_classes = (permissions.IsAuthenticated,)
    # Invocamos la petición GET para obtener todos los administradores
    def get(self, request, *args, **kwargs):
        admin = Administradores.objects.filter(user__is_active = 1).order_by("id")
        lista = AdminSerializer(admin, many=True).data
        return Response(lista, 200)

class AdminView(generics.CreateAPIView):
    def get_permissions(self):
        if self.request.method in ("GET", "PUT", "DELETE"):
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get(self, request, *args, **kwargs):
        admin_id = request.GET.get("id")
        admin = Administradores.objects.filter(id=admin_id).first()
        if admin is None:
            admin = get_object_or_404(Administradores, user_id=admin_id)
        admin = AdminSerializer(admin, many=False).data
        return Response(admin, 200)

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

            admin = Administradores.objects.create(user=user,
                                                    id_admin=request.data["id_admin"],
                                                    telefono=request.data["telefono"],
                                                    edad=request.data["edad"],
                                                    fecha_nacimiento=request.data["fecha_nacimiento"]
                                                    )

            admin.save()

            return Response({"admin_created_id": admin.id }, 201)

        return Response(user.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @transaction.atomic
    def put(self, request, *args, **kwargs):
        admin = get_object_or_404(Administradores, id=request.data["id"])
        admin.id_admin = request.data["id_admin"]
        admin.telefono = request.data["telefono"]
        admin.edad = request.data["edad"]
        admin.fecha_nacimiento = request.data["fecha_nacimiento"]
        admin.save()

        user = admin.user
        user.first_name = request.data["first_name"]
        user.last_name = request.data["last_name"]
        user.save()

        return Response({"message": "Administrador actualizado correctamente", "admin": AdminSerializer(admin).data}, 200)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        admin = get_object_or_404(Administradores, id=request.GET.get("id"))
        try:
            admin.user.delete()
            return Response({"details": "Administrador eliminado"}, 200)
        except Exception:
            return Response({"details": "Algo pasó al eliminar"}, 400)
        

class TotalUsers(generics.CreateAPIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        admin_qs = Administradores.objects.filter(user__is_active=True)
        total_admins = admin_qs.count()

        trabajadores_qs = Trabajadores.objects.filter(user__is_active=True)
        total_trabajadores = trabajadores_qs.count()

        return Response(
            {
                "admins": total_admins,
                "trabajadores": total_trabajadores
            },
            status=200
        )


class ChangePasswordView(generics.GenericAPIView):
    permission_classes = (permissions.IsAuthenticated,)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        role = request.data.get("role")
        target_id = request.data.get("target_id")
        new_password = request.data.get("new_password")
        confirm_password = request.data.get("confirm_password")

        if role not in ("administrador", "trabajador") or not target_id:
            return Response({"detail": "El usuario seleccionado no es válido"}, status=400)
        if not new_password or new_password != confirm_password:
            return Response({"detail": "Las contraseñas no coinciden"}, status=400)
        if len(new_password) < 6:
            return Response({"detail": "La contraseña debe tener al menos 6 caracteres"}, status=400)

        profile_model = Administradores if role == "administrador" else Trabajadores
        profile = profile_model.objects.filter(id=target_id).first()
        if profile is None and role == "administrador":
            profile = get_object_or_404(profile_model, user_id=target_id)
        elif profile is None:
            return Response({"detail": "El usuario seleccionado no existe"}, status=404)
        is_administrator = request.user.groups.filter(name="administrador").exists()

        if not is_administrator:
            if role != "trabajador" or profile.user_id != request.user.id:
                return Response({"detail": "No tienes permisos para cambiar esta contraseña"}, status=403)
            if not request.user.check_password(request.data.get("current_password", "")):
                return Response({"detail": "La contraseña actual es incorrecta"}, status=400)

        profile.user.set_password(new_password)
        profile.user.save(update_fields=["password"])
        return Response({"message": "Contraseña actualizada correctamente"}, status=200)
