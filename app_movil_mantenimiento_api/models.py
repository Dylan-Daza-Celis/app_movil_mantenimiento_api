from django.db import models
from django.contrib.auth.models import User
from rest_framework.authentication import TokenAuthentication
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

class BearerTokenAuthentication(TokenAuthentication):
    keyword = "Bearer"

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if (timezone.now() - token.created).total_seconds() >= settings.AUTH_TOKEN_MAX_AGE_SECONDS:
            raise AuthenticationFailed("La sesión expiró. Inicia sesión nuevamente.")
        return user, token

class TicketCounter(models.Model):
    fecha = models.DateField(primary_key=True)
    ultimo = models.PositiveIntegerField(default=0)


class Administradores(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=False, blank=False, default=None)
    id_admin = models.CharField(max_length=255, null=True, blank=True)
    telefono = models.CharField(max_length=255, null=True, blank=True)
    edad = models.IntegerField(null=True, blank=True)
    fecha_nacimiento = models.CharField(max_length=255, null=True, blank=True)
    creation = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    update = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return "Perfil del admin" +self.user.first_name+" "+self.user.last_name

class Trabajadores(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=False, blank=False, default=None)
    id_trabajador = models.CharField(max_length=255, null=True, blank=True)
    telefono = models.CharField(max_length=255, null=True, blank=True)
    fecha_nacimiento = models.CharField(max_length=255, null=True, blank=True)
    biblioteca= models.CharField(max_length=255, null=True, blank=True)
    edad = models.IntegerField(null=True, blank=True)
    departamento = models.CharField(max_length=255, null=True, blank=True)
    is_validated = models.BooleanField(default=False)
    creation = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    update = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return "Perfil del trabajador" +self.user.first_name+" "+self.user.last_name


def default_ticket_id():
    from .ticket_numbers import next_ticket_number
    return next_ticket_number()


class Ticket(models.Model):
    ESTATUS_PENDIENTE = "pendiente"
    ESTATUS_EN_PROCESO = "en_proceso"
    ESTATUS_RESUELTO = "resuelto"
    ESTATUS_CHOICES = (
        (ESTATUS_PENDIENTE, "Pendiente"),
        (ESTATUS_EN_PROCESO, "En proceso"),
        (ESTATUS_RESUELTO, "Resuelto"),
    )

    id_ticket = models.CharField(max_length=14, primary_key=True, default=default_ticket_id, editable=False)

    @property
    def numero_ticket(self):
        # Compatibility alias: there is only one identifier stored in the database.
        return self.id_ticket
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, related_name="tickets")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    respuesta_usuario = models.TextField(null=True, blank=True)
    estatus = models.CharField(
        max_length=20,
        choices=ESTATUS_CHOICES,
        default=ESTATUS_PENDIENTE,
    )
    prioridad = models.CharField(max_length=20, null=True, blank=True)
    inventario = models.CharField(max_length=10)
    marca = models.CharField(max_length=60)
    equipo = models.JSONField(default=dict)
    edificio = models.CharField(max_length=100)
    area = models.CharField(max_length=100)
    descripcion = models.TextField(max_length=1000)
    descripcion_reparacion = models.TextField(max_length=1000, null=True, blank=True)
    fecha_respuesta = models.DateTimeField(null=True, blank=True)
    fecha_modificacion = models.DateTimeField(null=True, blank=True)
    fecha_finalizacion = models.DateTimeField(null=True, blank=True, db_index=True)
    finalizado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_finalizados')
    solicitante_snapshot = models.JSONField(default=dict, blank=True)
    sistema_operativo = models.CharField(max_length=30, null=True, blank=True)
    problema = models.JSONField(default=dict)

    def __str__(self):
        return f"Ticket {self.id_ticket}"


class Notificacion(models.Model):
    TIPO_USUARIO_PENDIENTE = "usuario_pendiente"
    TIPO_TICKET_NUEVO = "ticket_nuevo"
    TIPO_USUARIO_VALIDADO = "usuario_validado"
    TIPO_MENSAJE_TICKET = "mensaje_ticket"

    destinatario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notificaciones",
    )
    tipo = models.CharField(max_length=30)
    mensaje = models.CharField(max_length=255)
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notificaciones",
    )
    leida = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return self.mensaje
