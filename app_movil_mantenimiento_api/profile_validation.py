from datetime import date, datetime
from functools import wraps

from django.db import IntegrityError

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import serializers


class ProfileInputSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=150, required=False)
    password = serializers.CharField(write_only=True, trim_whitespace=False, required=False)
    confirmar_password = serializers.CharField(write_only=True, trim_whitespace=False, required=False)
    telefono = serializers.RegexField(r"^\d{10}$")
    edad = serializers.IntegerField(min_value=18, max_value=120)
    fecha_nacimiento = serializers.CharField(max_length=255)
    id_admin = serializers.CharField(max_length=255, required=False)
    id_trabajador = serializers.CharField(max_length=255, required=False)
    departamento = serializers.CharField(max_length=255, required=False)
    biblioteca = serializers.CharField(max_length=255, required=False)

    def validate_fecha_nacimiento(self, value):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                born = datetime.strptime(value, fmt).date()
                break
            except ValueError:
                continue
        else:
            raise serializers.ValidationError("Ingresa una fecha válida.")
        if born > date.today():
            raise serializers.ValidationError("La fecha no puede estar en el futuro.")
        return born.isoformat()

    def validate(self, attrs):
        creating = self.context.get("creating", False)
        fields = ("id_admin",) if self.context["role"] == "administrador" else (
            "id_trabajador", "departamento", "biblioteca"
        )
        errors = {field: "Campo requerido." for field in fields if field not in attrs}
        if creating:
            if "email" not in attrs:
                errors["email"] = "Campo requerido."
            elif User.objects.filter(username__iexact=attrs["email"]).exists() or User.objects.filter(email__iexact=attrs["email"]).exists():
                errors["email"] = "Este correo ya está registrado."
            password = attrs.get("password", "")
            if password != attrs.get("confirmar_password"):
                errors["confirmar_password"] = "Las contraseñas no coinciden."
            try:
                validate_password(password, User(
                    username=attrs.get("email", ""), email=attrs.get("email", ""),
                    first_name=attrs.get("first_name", ""), last_name=attrs.get("last_name", "")
                ))
            except ValidationError as exc:
                errors["password"] = exc.messages
        if errors:
            raise serializers.ValidationError(errors)
        born = date.fromisoformat(attrs["fecha_nacimiento"])
        today = date.today()
        actual_age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if not 18 <= actual_age <= 120:
            raise serializers.ValidationError({"fecha_nacimiento": "La edad debe estar entre 18 y 120 años."})
        attrs["edad"] = actual_age
        return attrs


def profile_input(request, role, creating=False):
    serializer = ProfileInputSerializer(data=request.data, context={"role": role, "creating": creating})
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def registration_conflict(view):
    @wraps(view)
    def wrapped(self, request, *args, **kwargs):
        try:
            return view(self, request, *args, **kwargs)
        except IntegrityError:
            email = request.data.get("email")
            if isinstance(email, str) and User.objects.filter(username__iexact=email).exists():
                raise serializers.ValidationError({"email": ["Este correo ya está registrado."]})
            raise
    return wrapped
