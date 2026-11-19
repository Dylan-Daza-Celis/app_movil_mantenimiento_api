from django.contrib.auth.models import User
from rest_framework import serializers
from .models import *

class UserSerializer(serializers.ModelSerializer):
    id=serializers.IntegerField(read_only=True)
    first_name=serializers.CharField(required=True)
    last_name=serializers.CharField(required=True)
    email=serializers.EmailField(required=True)

    class Meta:
        model = User
        fields = ("id", "first_name", "last_name", "email")

class AdminSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    class Meta:
        model = Administradores
        fields = "__all__"

class TrabajadoresSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    class Meta:
        model = Trabajadores
        fields = "__all__"


class TicketSerializer(serializers.ModelSerializer):
    usuario = UserSerializer(read_only=True)
    numero_ticket = serializers.CharField(read_only=True)

    class Meta:
        model = Ticket
        fields = "__all__"


class TicketInputSerializer(serializers.Serializer):
    inventario = serializers.RegexField(r"^[0-9]{10}$")
    marca = serializers.CharField(max_length=60)
    edificio = serializers.CharField(max_length=100)
    area = serializers.CharField(max_length=100)
    descripcion = serializers.CharField(max_length=1000)
    equipo = serializers.JSONField()
    problema = serializers.JSONField()
    sistema_operativo = serializers.ChoiceField(
        choices=("Windows 10", "Windows 11", "MacOS", "Otro"), allow_null=True, required=False
    )
    estatus = serializers.ChoiceField(choices=Ticket.ESTATUS_CHOICES, required=False)
    prioridad = serializers.ChoiceField(choices=("critica", "alta", "media", "baja"), required=False, allow_null=True)
    respuesta_usuario = serializers.CharField(max_length=1000, required=False, allow_null=True, allow_blank=True)
    descripcion_reparacion = serializers.CharField(max_length=1000, required=False, allow_null=True, allow_blank=True)
    solucionado_por = serializers.CharField(max_length=500, required=False, allow_null=True, allow_blank=True)


class PasswordChangeSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=("administrador", "trabajador"))
    target_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    current_password = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False, max_length=4096)
    new_password = serializers.CharField(trim_whitespace=False, max_length=4096)
    confirm_password = serializers.CharField(trim_whitespace=False, max_length=4096)
