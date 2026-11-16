from datetime import datetime, timedelta, timezone as datetime_timezone
from dateutil.relativedelta import relativedelta

from django.db.models import Avg, DateTimeField, DurationField, ExpressionWrapper, F, Count
from django.db.models.functions import Coalesce, ExtractMonth, ExtractYear
from django.utils import timezone
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from app_movil_mantenimiento_api.models import Ticket, Trabajadores, Administradores
from app_movil_mantenimiento_api.permissions import IsValidatedUser, is_administrator
from .ticket import serializar_ticket

# Puebla uses UTC-6. A numeric offset also works on MariaDB without timezone tables.
HISTORY_TZ = datetime_timezone(timedelta(hours=-6))


class HistorialTickets(generics.GenericAPIView):
    permission_classes = (IsValidatedUser,)

    def get(self, request):
        admin = is_administrator(request.user)
        tickets = Ticket.objects.filter(estatus=Ticket.ESTATUS_RESUELTO)
        if not admin:
            tickets = tickets.filter(usuario=request.user)
        tickets = tickets.annotate(cierre=Coalesce('fecha_finalizacion', 'fecha_modificacion', 'fecha_creacion'))
        if not admin:
            end = timezone.now()
            start = end.astimezone(HISTORY_TZ) - relativedelta(months=1)
            # The worker's window is enforced here, regardless of year/month/page parameters.
            recent = list(tickets.filter(cierre__gte=start, cierre__lte=end)
                          .select_related('usuario', 'finalizado_por').order_by('-cierre', '-id_ticket'))
            profile = Trabajadores.objects.filter(user=request.user).first()
            request.ticket_profiles = ({request.user.id: profile} if profile else {}, set())
            return Response({
                'count': len(recent), 'next': None, 'previous': None,
                'results': [serializar_ticket(ticket, request) for ticket in recent],
                'periods': [], 'year': None, 'month': None, 'stats': None,
                'window_start': start, 'window_end': end,
            })
        calendar = ExpressionWrapper(F('cierre') - timedelta(hours=6), output_field=DateTimeField())
        periods = list(tickets.annotate(calendar=calendar).annotate(year=ExtractYear('calendar', tzinfo=datetime_timezone.utc), month=ExtractMonth('calendar', tzinfo=datetime_timezone.utc))
                       .values('year', 'month').annotate(total=Count('id_ticket')).order_by('-year', '-month'))
        try:
            year = int(request.query_params.get('year', periods[0]['year'] if periods else timezone.now().astimezone(HISTORY_TZ).year))
            month = int(request.query_params['month']) if request.query_params.get('month') else None
            if not 1 <= year <= 9998 or (month is not None and not 1 <= month <= 12):
                raise ValueError()
        except (TypeError, ValueError):
            raise ValidationError({'detail': 'Selecciona un año y un mes válidos.'})
        start = datetime(year, 1, 1, tzinfo=HISTORY_TZ)
        annual = tickets.filter(cierre__gte=start, cierre__lt=datetime(year + 1, 1, 1, tzinfo=HISTORY_TZ))
        stats = None
        if admin:
            duration = ExpressionWrapper(F('fecha_finalizacion') - F('fecha_creacion'), output_field=DurationField())
            known = annual.filter(fecha_finalizacion__isnull=False, fecha_finalizacion__gte=F('fecha_creacion'))
            average = known.aggregate(value=Avg(duration))['value']
            stats = {
                'total': annual.count(),
                'average_hours': round(average.total_seconds() / 3600, 1) if average is not None else None,
                'measured_count': known.count(),
                'monthly': [{'month': m, 'total': sum(p['total'] for p in periods if p['year'] == year and p['month'] == m)} for m in range(1, 13)],
                'priorities': dict(annual.order_by().values('prioridad').annotate(total=Count('id_ticket')).values_list('prioridad', 'total')),
            }
        filtered = annual
        if month:
            end = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1, tzinfo=HISTORY_TZ)
            filtered = filtered.filter(cierre__gte=datetime(year, month, 1, tzinfo=HISTORY_TZ), cierre__lt=end)
        page = self.paginate_queryset(filtered.select_related('usuario', 'finalizado_por').order_by('-cierre', '-id_ticket'))
        ids = {ticket.usuario_id for ticket in page}
        request.ticket_profiles = (
            {p.user_id: p for p in Trabajadores.objects.filter(user_id__in=ids).order_by('-id')},
            set(Administradores.objects.filter(user_id__in=ids).values_list('user_id', flat=True)),
        )
        response = self.get_paginated_response([serializar_ticket(ticket, request) for ticket in page])
        response.data.update(periods=periods, year=year, month=month, stats=stats)
        return response
