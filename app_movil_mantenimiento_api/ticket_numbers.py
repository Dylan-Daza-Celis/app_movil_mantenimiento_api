from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Ticket, TicketCounter


@transaction.atomic
def next_ticket_number():
    today = timezone.localdate()
    # A persistent row serializes allocation even if tickets have been deleted.
    counter, _ = TicketCounter.objects.get_or_create(fecha=today)
    counter = TicketCounter.objects.select_for_update().get(pk=counter.pk)
    prefix = f"MANT-{today:%y%m%d}"
    last = Ticket.objects.filter(id_ticket__startswith=prefix).order_by("-id_ticket").values_list("id_ticket", flat=True).first()
    existing = int(last[-3:]) if last and last[-3:].isdigit() else 0
    counter.ultimo = max(counter.ultimo, existing) + 1
    if counter.ultimo > 999:
        raise ValidationError({"detail": "Se alcanzó el límite diario de tickets."})
    counter.save(update_fields=["ultimo"])
    return f"{prefix}{counter.ultimo:03d}"
