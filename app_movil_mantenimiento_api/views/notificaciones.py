from app_movil_mantenimiento_api.validation import positive_id
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from app_movil_mantenimiento_api.models import Notificacion


class NotificacionesView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        if request.query_params.get("summary") == "true":
            return Response({"unread_count": Notificacion.objects.filter(destinatario=request.user, leida=False).count()})
        notificaciones = Notificacion.objects.filter(
            destinatario=request.user
        ).select_related("ticket")[:50]
        return Response(
            [
                {
                    "id": notificacion.id,
                    "tipo": notificacion.tipo,
                    "mensaje": notificacion.mensaje,
                    "leida": notificacion.leida,
                    "fecha_creacion": notificacion.fecha_creacion,
                    "ticket_id": notificacion.ticket_id,
                    "numero_ticket": (
                        notificacion.ticket.numero_ticket
                        if notificacion.ticket
                        else None
                    ),
                }
                for notificacion in notificaciones
            ],
            status=status.HTTP_200_OK,
        )

    def patch(self, request, *args, **kwargs):
        notificacion = Notificacion.objects.filter(
            id=positive_id(request.data.get("id")),
            destinatario=request.user,
        ).first()
        if notificacion is None:
            return Response(
                {"detail": "Notificación no encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        notificacion.leida = True
        notificacion.save(update_fields=["leida"])
        return Response({"message": "Notificación marcada como leída."})
