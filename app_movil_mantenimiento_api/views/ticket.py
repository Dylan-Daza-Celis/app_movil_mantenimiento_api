from django.db import transaction
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from app_movil_mantenimiento_api.models import (
    Administradores,
    Notificacion,
    Ticket,
    Trabajadores,
)
from app_movil_mantenimiento_api.serializers import TicketSerializer


PRIORIDAD_CRITICA = "critica"
PRIORIDAD_ALTA = "alta"
PRIORIDAD_MEDIA = "media"
PRIORIDAD_BAJA = "baja"

PROBLEMAS_CRITICOS = {
    "No se puede acceder a una página web o correo institucional",
}

PROBLEMAS_ALTOS = {
    "No enciende",
    "No activa libros",
    "No desactiva libros",
    "No se activa",
    "Genera falsas alarmas",
    "No imprime",
    "Falla de conexión",
    "No alimenta a los dispositivos",
    "Falla en la licencia de Office",
}

PROBLEMAS_MEDIOS = {
    "No tiene conexión a internet",
    "Falla en teclado/mouse",
    "Falla en cámara/bocinas",
    "Falla el contador",
    "Imprime con mala calidad",
    "Atasco de papel",
    "Truena cuando se enciende",
}


def serializar_ticket(ticket, request):
    data = TicketSerializer(ticket).data
    trabajador = Trabajadores.objects.select_related("user").filter(user_id=ticket.usuario_id).first()
    administrador = Administradores.objects.select_related("user").filter(user_id=ticket.usuario_id).first()
    data["solicitante"] = {
        "nombre": (
            f"{ticket.usuario.first_name} {ticket.usuario.last_name}"
        ).strip(),
        "biblioteca": trabajador.biblioteca if trabajador else None,
        "puesto": trabajador.departamento if trabajador else None,
        "rol": "trabajador" if trabajador else "administrador" if administrador else None,
    }
    if request.user.groups.filter(name="trabajador").exists():
        data.pop("prioridad", None)
    return data


def generar_numero_ticket():
    fecha = timezone.localdate()
    cantidad = Ticket.objects.filter(fecha_creacion__date=fecha).count() + 1
    if cantidad > 999:
        raise ValueError("Se alcanzó el límite diario de tickets.")
    return f"MANT-{fecha:%y%m%d}{cantidad:03d}"


class TicketView(generics.CreateAPIView):
    def get_permissions(self):
        if self.request.method in ("GET", "POST", "PUT", "DELETE"):
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get(self, request, *args, **kwargs):
        ticket = get_object_or_404(Ticket, id_ticket=request.GET.get("id"))
        if not self.puede_consultar(ticket, request):
            return Response(
                {"detail": "No tienes permiso para consultar este ticket."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(serializar_ticket(ticket, request), status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        errores = self.validar_ticket(request.data)
        if errores:
            return Response(errores, status=status.HTTP_400_BAD_REQUEST)

        ticket = Ticket.objects.create(
            usuario=request.user,
            numero_ticket=generar_numero_ticket(),
            estatus=Ticket.ESTATUS_PENDIENTE,
            prioridad=self.calcular_prioridad(
                request.data["equipo"],
                request.data["problema"],
            ),
            respuesta_usuario=None,
            fecha_respuesta=None,
            inventario=request.data["inventario"],
            marca=request.data["marca"],
            equipo=request.data["equipo"],
            edificio=request.data["edificio"],
            area=request.data["area"],
            descripcion=request.data["descripcion"],
            sistema_operativo=request.data.get("sistema_operativo"),
            problema=request.data["problema"],
        )
        administradores = User.objects.filter(
            groups__name="administrador"
        ).distinct()
        Notificacion.objects.bulk_create(
            [
                Notificacion(
                    destinatario=administrador,
                    tipo=Notificacion.TIPO_TICKET_NUEVO,
                    mensaje=f"Se reportó un nuevo ticket: {ticket.numero_ticket}.",
                    ticket=ticket,
                )
                for administrador in administradores
            ]
        )
        return Response(
            {
                "ticket_created_id": ticket.id_ticket,
                "numero_ticket": ticket.numero_ticket,
            },
            status=status.HTTP_201_CREATED,
        )

    @transaction.atomic
    def put(self, request, *args, **kwargs):
        ticket = get_object_or_404(
            Ticket,
            id_ticket=request.data.get("id_ticket"),
        )
        if not self.puede_actualizar(ticket, request):
            return Response(
                {"detail": "No tienes permiso para actualizar este ticket."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not self.es_administrador(request) and any(
            campo in request.data
            for campo in ("estatus", "prioridad", "respuesta_usuario", "descripcion_reparacion")
        ):
            return Response(
                {"detail": "Solo un administrador puede actualizar el seguimiento del ticket."},
                status=status.HTTP_403_FORBIDDEN,
            )

        datos = dict(request.data)
        respuesta_anterior = ticket.respuesta_usuario
        errores = self.validar_ticket(datos, actualizar=True)
        if errores:
            return Response(errores, status=status.HTTP_400_BAD_REQUEST)

        for campo in (
            "inventario",
            "marca",
            "equipo",
            "edificio",
            "area",
            "descripcion",
            "sistema_operativo",
            "problema",
        ):
            if campo in datos:
                setattr(ticket, campo, datos[campo])

        ticket.prioridad = self.calcular_prioridad(
            ticket.equipo,
            ticket.problema,
        )

        if self.es_administrador(request):
            for campo in ("estatus", "prioridad", "respuesta_usuario"):
                if campo in datos:
                    setattr(ticket, campo, datos[campo])
            if "respuesta_usuario" in datos and datos["respuesta_usuario"]:
                ticket.fecha_respuesta = timezone.now()
            if "estatus" in datos and datos["estatus"] == Ticket.ESTATUS_RESUELTO:
                descripcion_reparacion = datos.get("descripcion_reparacion", "").strip()
                if not descripcion_reparacion:
                    return Response(
                        {"descripcion_reparacion": "Describe la reparación realizada."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                ticket.descripcion_reparacion = descripcion_reparacion
                ticket.fecha_modificacion = timezone.now()
            elif "estatus" in datos:
                ticket.fecha_modificacion = timezone.now()

        ticket.save()
        respuesta_nueva = ticket.respuesta_usuario
        if (
            self.es_administrador(request)
            and respuesta_nueva
            and respuesta_nueva != respuesta_anterior
        ):
            Notificacion.objects.create(
                destinatario=ticket.usuario,
                tipo=Notificacion.TIPO_MENSAJE_TICKET,
                mensaje=(
                    f"El administrador dejó un mensaje sobre el ticket "
                    f"{ticket.numero_ticket}."
                ),
                ticket=ticket,
            )
        return Response(
            {
                "message": "Ticket actualizado correctamente",
                "ticket": serializar_ticket(ticket, request),
            },
            status=status.HTTP_200_OK,
        )

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        ticket = get_object_or_404(Ticket, id_ticket=request.GET.get("id"))
        es_administrador = request.user.groups.filter(name="administrador").exists()
        es_trabajador = request.user.groups.filter(name="trabajador").exists()
        if not es_administrador and (
            not es_trabajador or ticket.usuario_id != request.user.id
        ):
            return Response(
                {"detail": "Solo puedes cancelar tus propios tickets."},
                status=status.HTTP_403_FORBIDDEN,
            )
        ticket.delete()
        return Response({"details": "Ticket eliminado"}, status=status.HTTP_200_OK)

    @staticmethod
    def es_revisor(request):
        return request.user.groups.filter(
            name__in=("administrador", "trabajador")
        ).exists()

    @staticmethod
    def es_administrador(request):
        return request.user.groups.filter(name="administrador").exists()

    @staticmethod
    def puede_consultar(ticket, request):
        return (
            ticket.usuario_id == request.user.id
            or TicketView.es_administrador(request)
        )

    @staticmethod
    def puede_actualizar(ticket, request):
        return (
            ticket.usuario_id == request.user.id
            or TicketView.es_administrador(request)
        )

    @staticmethod
    def validar_ticket(data, actualizar=False):
        errores = {}
        campos = (
            "inventario",
            "marca",
            "equipo",
            "edificio",
            "area",
            "descripcion",
            "problema",
        )

        if not actualizar:
            for campo in campos:
                if campo not in data or data[campo] in ("", None):
                    errores[campo] = "Campo requerido."

        inventario = data.get("inventario")
        if inventario is not None and (
            not str(inventario).isdigit() or len(str(inventario)) != 10
        ):
            errores["inventario"] = "El inventario debe contener 10 números."

        equipo = data.get("equipo")
        equipos_validos = {"1", "2", "3", "4", "5", "6"}
        if equipo is not None:
            if not isinstance(equipo, dict) or equipo.get("value") not in equipos_validos:
                errores["equipo"] = "Selecciona un equipo válido."
            elif equipo["value"] == "6" and not equipo.get("descripcion"):
                errores["equipo"] = "Describe el equipo seleccionado."
            elif equipo["value"] != "6" and equipo.get("descripcion") is not None:
                errores["equipo"] = "La descripción debe ser null."

        sistema = data.get("sistema_operativo")
        if equipo and isinstance(equipo, dict) and equipo.get("value") == "1":
            if not sistema:
                errores["sistema_operativo"] = "Campo requerido para computadoras."
        elif sistema is not None:
            errores["sistema_operativo"] = "Solo aplica a computadoras."

        problema = data.get("problema")
        if problema is not None and not isinstance(problema, dict):
            errores["problema"] = "Selecciona un problema válido."
        elif problema and equipo and isinstance(equipo, dict):
            problemas = {
                "1": {"No enciende", "No tiene conexión a internet", "Hace un ruido raro", "Falla en la licencia de Office", "Falla en teclado/mouse", "Falla en cámara/bocinas", "No se puede acceder a una página web o correo institucional", "Otro"},
                "2": {"No activa libros", "No desactiva libros", "No enciende", "Otro"},
                "3": {"No se activa", "Falla el contador", "Genera falsas alarmas", "No enciende", "Otro"},
                "4": {"No imprime", "Imprime con mala calidad", "Atasco de papel", "Falla de conexión", "Otro"},
                "5": {"No enciende", "Truena cuando se enciende", "No alimenta a los dispositivos", "Otro"},
                "6": {"Falla general", "Falla de alimentación", "Otro"},
            }
            valor = problema.get("value")
            if valor not in problemas.get(equipo.get("value"), set()):
                errores["problema"] = "Selecciona un problema válido."
            elif valor == "Otro" and not problema.get("descripcion"):
                errores["problema"] = "Describe el problema seleccionado."
            elif valor != "Otro" and problema.get("descripcion") is not None:
                errores["problema"] = "La descripción debe ser null."

        return errores

    @staticmethod
    def calcular_prioridad(equipo, problema):
        equipo_value = equipo.get("value") if isinstance(equipo, dict) else None
        problema_value = problema.get("value") if isinstance(problema, dict) else None

        if equipo_value == "3" or problema_value in PROBLEMAS_CRITICOS:
            return PRIORIDAD_CRITICA

        if (
            equipo_value in {"1", "2", "4", "5"}
            and problema_value in PROBLEMAS_ALTOS
        ):
            return PRIORIDAD_ALTA

        if problema_value in PROBLEMAS_MEDIOS:
            return PRIORIDAD_MEDIA

        return PRIORIDAD_BAJA


class TicketsAll(generics.CreateAPIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        if request.user.groups.filter(name="administrador").exists():
            tickets = Ticket.objects.all().order_by("-fecha_creacion")
        elif request.user.groups.filter(name="trabajador").exists():
            tickets = Ticket.objects.filter(usuario=request.user).order_by("-fecha_creacion")
        else:
            tickets = Ticket.objects.filter(usuario=request.user).order_by("-fecha_creacion")
        lista = [serializar_ticket(ticket, request) for ticket in tickets]
        return Response(lista, status=status.HTTP_200_OK)
