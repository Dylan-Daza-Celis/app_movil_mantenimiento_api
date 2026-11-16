from app_movil_mantenimiento_api.validation import ticket_id
from app_movil_mantenimiento_api.permissions import IsValidatedUser
from app_movil_mantenimiento_api.ticket_numbers import next_ticket_number
from app_movil_mantenimiento_api.serializers import TicketInputSerializer
from app_movil_mantenimiento_api.transactions import retry_transaction
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, Value, When
from rest_framework.exceptions import ValidationError
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
    data['fecha_cierre'] = ticket.fecha_finalizacion or ticket.fecha_modificacion or ticket.fecha_creacion if ticket.estatus == Ticket.ESTATUS_RESUELTO else None
    data['cierre_estimado'] = ticket.estatus == Ticket.ESTATUS_RESUELTO and ticket.fecha_finalizacion is None
    data['atendido_por'] = ticket.finalizado_por.get_full_name() if ticket.finalizado_por_id else None
    if hasattr(request, "ticket_profiles"):
        trabajadores, administradores = request.ticket_profiles
        trabajador = trabajadores.get(ticket.usuario_id)
        administrador = ticket.usuario_id in administradores
    else:
        trabajador = Trabajadores.objects.filter(user_id=ticket.usuario_id).first()
        administrador = Administradores.objects.filter(user_id=ticket.usuario_id).exists()
    data["solicitante"] = {
        "nombre": (
            f"{ticket.usuario.first_name} {ticket.usuario.last_name}"
        ).strip(),
        "biblioteca": trabajador.biblioteca if trabajador else None,
        "puesto": trabajador.departamento if trabajador else None,
        "rol": "trabajador" if trabajador else "administrador" if administrador else None,
    }
    if ticket.solicitante_snapshot:
        data['solicitante'] = ticket.solicitante_snapshot
    if not TicketView.es_administrador(request):
        data.pop("prioridad", None)
    return data


def generar_numero_ticket():
    return next_ticket_number()


class TicketView(generics.GenericAPIView):
    permission_classes = (IsValidatedUser,)

    def get(self, request, *args, **kwargs):
        ticket = get_object_or_404(Ticket, id_ticket=ticket_id(request.GET.get("id")))
        if not self.puede_consultar(ticket, request):
            return Response(
                {"detail": "No tienes permiso para consultar este ticket."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(serializar_ticket(ticket, request), status=status.HTTP_200_OK)

    @retry_transaction
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = TicketInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        errores = self.validar_ticket(serializer.validated_data)
        if errores:
            return Response(errores, status=status.HTTP_400_BAD_REQUEST)

        perfil = Trabajadores.objects.filter(user=request.user).first()
        ticket = Ticket.objects.create(
            usuario=request.user,
            solicitante_snapshot={
                'nombre': request.user.get_full_name(), 'email': request.user.email,
                'biblioteca': perfil.biblioteca if perfil else None,
                'puesto': perfil.departamento if perfil else None,
                'rol': 'administrador' if self.es_administrador(request) else 'trabajador',
            },
            id_ticket=generar_numero_ticket(),
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
            Ticket.objects.select_for_update(),
            id_ticket=ticket_id(request.data.get("id_ticket")),
        )
        if not self.puede_actualizar(ticket, request):
            return Response(
                {"detail": "No tienes permiso para actualizar este ticket."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if ticket.estatus == Ticket.ESTATUS_RESUELTO:
            return Response({'detail': 'El reporte ya está finalizado y se conserva en el historial.'}, status=409)
        if not self.es_administrador(request) and any(
            campo in request.data
            for campo in ("estatus", "prioridad", "respuesta_usuario", "descripcion_reparacion")
        ):
            return Response(
                {"detail": "Solo un administrador puede actualizar el seguimiento del ticket."},
                status=status.HTTP_403_FORBIDDEN,
            )

        datos = dict(request.data)
        # Validate the resulting record, including fields omitted by a partial update.
        merged = {field: getattr(ticket, field) for field in (
            "inventario", "marca", "equipo", "edificio", "area", "descripcion",
            "sistema_operativo", "problema", "estatus", "prioridad",
            "respuesta_usuario", "descripcion_reparacion"
        )}
        merged.update(datos)
        serializer = TicketInputSerializer(data=merged)
        serializer.is_valid(raise_exception=True)
        respuesta_anterior = ticket.respuesta_usuario
        errores = self.validar_ticket(serializer.validated_data)
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

        if "equipo" in datos or "problema" in datos:
            ticket.prioridad = self.calcular_prioridad(ticket.equipo, ticket.problema)

        if self.es_administrador(request):
            for campo in ("estatus", "prioridad", "respuesta_usuario"):
                if campo in datos:
                    setattr(ticket, campo, datos[campo])
            if "respuesta_usuario" in datos and datos["respuesta_usuario"]:
                ticket.fecha_respuesta = timezone.now()
            if "estatus" in datos and datos["estatus"] == Ticket.ESTATUS_RESUELTO:
                descripcion_reparacion = (datos.get("descripcion_reparacion") or ticket.descripcion_reparacion or "").strip()
                if not descripcion_reparacion:
                    return Response(
                        {"descripcion_reparacion": "Describe la reparación realizada."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                ticket.descripcion_reparacion = descripcion_reparacion
                ticket.fecha_finalizacion = timezone.now()
                ticket.finalizado_por = request.user
                ticket.fecha_modificacion = timezone.now()
            elif "estatus" in datos:
                ticket.fecha_modificacion = timezone.now()

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
        ticket = get_object_or_404(Ticket.objects.select_for_update(), id_ticket=ticket_id(request.GET.get("id")))
        es_administrador = request.user.groups.filter(name="administrador").exists()
        es_trabajador = request.user.groups.filter(name="trabajador").exists()
        if not es_administrador and (
            not es_trabajador or ticket.usuario_id != request.user.id
        ):
            return Response(
                {"detail": "Solo puedes cancelar tus propios tickets."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not es_administrador and ticket.estatus == Ticket.ESTATUS_RESUELTO:
            return Response({"detail": "No puedes cancelar un ticket finalizado."}, status=403)
        ticket.delete()
        return Response({"details": "Ticket eliminado"}, status=status.HTTP_200_OK)

    @staticmethod
    def es_revisor(request):
        return request.user.groups.filter(
            name__in=("administrador", "trabajador")
        ).exists()

    @staticmethod
    def es_administrador(request):
        if not hasattr(request, "ticket_is_admin"):
            request.ticket_is_admin = request.user.groups.filter(name="administrador").exists()
        return request.ticket_is_admin

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
            if not isinstance(equipo, dict) or not isinstance(equipo.get("value"), str) or equipo.get("value") not in equipos_validos:
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
        elif isinstance(problema, dict) and isinstance(equipo, dict):
            problemas = {
                "1": {"No enciende", "No tiene conexión a internet", "Hace un ruido raro", "Falla en la licencia de Office", "Falla en teclado/mouse", "Falla en cámara/bocinas", "No se puede acceder a una página web o correo institucional", "Otro"},
                "2": {"No activa libros", "No desactiva libros", "No enciende", "Otro"},
                "3": {"No se activa", "Falla el contador", "Genera falsas alarmas", "No enciende", "Otro"},
                "4": {"No imprime", "Imprime con mala calidad", "Atasco de papel", "Falla de conexión", "Otro"},
                "5": {"No enciende", "Truena cuando se enciende", "No alimenta a los dispositivos", "Otro"},
                "6": {"Falla general", "Falla de alimentación", "Otro"},
            }
            valor = problema.get("value")
            if not isinstance(valor, str) or valor not in problemas.get(str(equipo.get("value")), set()):
                errores["problema"] = "Selecciona un problema válido."
            elif valor == "Otro" and not problema.get("descripcion"):
                errores["problema"] = "Describe el problema seleccionado."
            elif valor != "Otro" and problema.get("descripcion") is not None:
                errores["problema"] = "La descripción debe ser null."

        for field, value, limit in (("equipo", equipo, 100), ("problema", problema, 200)):
            if isinstance(value, dict) and value.get("descripcion") is not None:
                description = value["descripcion"]
                if not isinstance(description, str) or not description.strip() or len(description) > limit:
                    errores[field] = f"La descripcion debe ser texto de hasta {limit} caracteres."
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


class TicketsAll(generics.GenericAPIView):
    permission_classes = (IsValidatedUser,)

    def get(self, request, *args, **kwargs):
        if request.user.groups.filter(name="administrador").exists():
            tickets = Ticket.objects.select_related("usuario").all().order_by("-fecha_creacion")
        elif request.user.groups.filter(name="trabajador").exists():
            tickets = Ticket.objects.select_related("usuario").filter(usuario=request.user).order_by("-fecha_creacion")
        else:
            tickets = Ticket.objects.select_related("usuario").filter(usuario=request.user).order_by("-fecha_creacion")
        tickets = tickets.exclude(estatus=Ticket.ESTATUS_RESUELTO)
        prioridad = request.query_params.get("prioridad", "")
        biblioteca = request.query_params.get("biblioteca", "")
        if prioridad:
            if not TicketView.es_administrador(request):
                return Response({"detail": "Solo los administradores pueden filtrar por prioridad."}, status=403)
            if prioridad not in ("critica", "alta", "media", "baja"):
                raise ValidationError({"prioridad": "Selecciona una prioridad válida."})
        original_libraries = tickets.exclude(solicitante_snapshot={}).order_by().values_list('solicitante_snapshot__biblioteca', flat=True).distinct()
        legacy_libraries = Trabajadores.objects.filter(user_id__in=tickets.filter(solicitante_snapshot={}).values('usuario_id')).values_list('biblioteca', flat=True)
        bibliotecas = sorted({value for value in [*original_libraries, *legacy_libraries] if isinstance(value, str) and value})
        summary = None
        if "page" in request.query_params:
            pending = tickets.exclude(estatus=Ticket.ESTATUS_RESUELTO)
            summary = {
                "pending_count": pending.count(),
                "priority_counts": dict(pending.order_by().values("prioridad").annotate(total=Count("id_ticket")).values_list("prioridad", "total")) if TicketView.es_administrador(request) else {},
            }
        if prioridad:
            tickets = tickets.filter(prioridad=prioridad)
        if biblioteca:
            tickets = tickets.filter(Q(solicitante_snapshot__biblioteca=biblioteca) | Q(solicitante_snapshot={}, usuario_id__in=Trabajadores.objects.filter(biblioteca=biblioteca).values('user_id')))
        if "page" in request.query_params:
            tickets = tickets.annotate(
                closed_order=Case(When(estatus=Ticket.ESTATUS_RESUELTO, then=Value(1)), default=Value(0), output_field=IntegerField()),
                priority_order=Case(
                    When(prioridad="critica", then=Value(0)), When(prioridad="alta", then=Value(1)),
                    When(prioridad="media", then=Value(2)), default=Value(3), output_field=IntegerField(),
                ),
            )
            order = ["closed_order"]
            if TicketView.es_administrador(request):
                order.append("priority_order")
            tickets = tickets.order_by(*order, "-fecha_creacion", "-id_ticket")
            tickets = self.paginate_queryset(tickets)
        tickets = list(tickets)
        user_ids = {ticket.usuario_id for ticket in tickets}
        request.ticket_profiles = (
            {profile.user_id: profile for profile in Trabajadores.objects.filter(user_id__in=user_ids).order_by("-id")},
            set(Administradores.objects.filter(user_id__in=user_ids).values_list("user_id", flat=True)),
        )
        lista = [serializar_ticket(ticket, request) for ticket in tickets]
        if summary is not None:
            response = self.get_paginated_response(lista)
            response.data["summary"] = summary
            response.data["filters"] = {"bibliotecas": bibliotecas}
            return response
        return Response(lista, status=status.HTTP_200_OK)
