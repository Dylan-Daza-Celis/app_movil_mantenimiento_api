from django.db.models.deletion import ProtectedError
from django.utils import timezone
from app_movil_mantenimiento_api.validation import positive_id
from app_movil_mantenimiento_api.permissions import IsAdministrator
from app_movil_mantenimiento_api.profile_validation import profile_input, registration_conflict
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework.authtoken.models import Token
from django.db import transaction
from app_movil_mantenimiento_api.serializers import UserSerializer
from app_movil_mantenimiento_api.serializers import AdminSerializer, TrabajadoresSerializer, PasswordChangeSerializer
from app_movil_mantenimiento_api.models import Administradores, Trabajadores, Notificacion
from django.contrib.auth.models import User
from rest_framework import permissions
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404


class AdminAll(generics.GenericAPIView):
    #Esta función es esencial para todo donde se requiera autorización de inicio de sesión (token)
    permission_classes = (IsAdministrator,)
    # Invocamos la petición GET para obtener todos los administradores
    def get(self, request, *args, **kwargs):
        admin = Administradores.objects.select_related("user").filter(user__is_active = 1).order_by("id")
        lista = AdminSerializer(admin, many=True).data
        return Response(lista, 200)

class AdminView(generics.GenericAPIView):
    permission_classes = (IsAdministrator,)

    def get(self, request, *args, **kwargs):
        admin_id = positive_id(request.GET.get("id"))
        admin = Administradores.objects.filter(id=admin_id).first()
        if admin is None:
            return Response({"detail": "Administrador no encontrado"}, status=404)
        admin = AdminSerializer(admin, many=False).data
        return Response(admin, 200)

    @registration_conflict
    @transaction.atomic
    def post(self, request, *args, **kwargs):

        validated = profile_input(request, "administrador", creating=True)
        user = UserSerializer(data=validated)

        if user.is_valid():
            #Grab user data
            role = "administrador"
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

            admin = Administradores.objects.create(user=user,
                                                    id_admin=validated["id_admin"],
                                                    telefono=validated["telefono"],
                                                    edad=validated["edad"],
                                                    fecha_nacimiento=validated["fecha_nacimiento"]
                                                    )

            admin.save()

            return Response({"admin_created_id": admin.id }, 201)

        return Response(user.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @transaction.atomic
    def put(self, request, *args, **kwargs):
        validated = profile_input(request, "administrador")
        admin = get_object_or_404(Administradores, id=positive_id(request.data.get("id")))
        admin.id_admin = validated["id_admin"]
        admin.telefono = validated["telefono"]
        admin.edad = validated["edad"]
        admin.fecha_nacimiento = validated["fecha_nacimiento"]
        admin.update = timezone.now()
        admin.save()

        user = admin.user
        user.first_name = validated["first_name"]
        user.last_name = validated["last_name"]
        user.save()

        return Response({"message": "Administrador actualizado correctamente", "admin": AdminSerializer(admin).data}, 200)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        admin = get_object_or_404(Administradores, id=positive_id(request.GET.get("id")))
        if admin.user_id == request.user.id:
            return Response({"detail": "No puedes eliminar tu propia cuenta desde este listado."}, status=400)
        try:
            admin.user.delete()
            return Response({"details": "Administrador eliminado"}, 200)
        except ProtectedError:
            return Response({"details": "El usuario tiene tickets asociados y no puede eliminarse"}, 400)
        

class TotalUsers(generics.GenericAPIView):
    permission_classes = (IsAdministrator,)

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
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        role = validated.get("role")
        target_id = positive_id(validated.get("target_id"))
        new_password = validated.get("new_password")
        confirm_password = validated.get("confirm_password")

        if role not in ("administrador", "trabajador") or not target_id:
            return Response({"detail": "El usuario seleccionado no es válido"}, status=400)
        if not new_password or new_password != confirm_password:
            return Response({"detail": "Las contraseñas no coinciden"}, status=400)
        if not isinstance(new_password, str):
            return Response({"detail": "La contraseña debe ser texto."}, status=400)

        profile_model = Administradores if role == "administrador" else Trabajadores
        profile = profile_model.objects.filter(id=target_id).first()
        if profile is None:
            return Response({"detail": "El usuario seleccionado no existe"}, status=404)
        is_administrator = request.user.groups.filter(name="administrador").exists()

        if not is_administrator:
            if role != "trabajador" or profile.user_id != request.user.id:
                return Response({"detail": "No tienes permisos para cambiar esta contraseña"}, status=403)
            if not request.user.check_password(validated.get("current_password", "")):
                return Response({"detail": "La contraseña actual es incorrecta"}, status=400)

        if profile.user_id == request.user.id and not request.user.check_password(validated.get("current_password", "")):
            return Response({"detail": "La contraseña actual es incorrecta"}, status=400)
        try:
            validate_password(new_password, profile.user)
        except ValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)
        profile.user.set_password(new_password)
        profile.user.save(update_fields=["password"])
        Token.objects.filter(user=profile.user).delete()
        result = {"message": "Contraseña actualizada correctamente"}
        if profile.user_id == request.user.id:
            result["token"] = Token.objects.create(user=profile.user).key
        return Response(result, status=200)
