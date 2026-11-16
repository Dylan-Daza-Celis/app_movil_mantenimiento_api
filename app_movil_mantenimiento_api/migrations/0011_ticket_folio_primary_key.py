import re
from datetime import datetime

from django.db import migrations, models
import django.db.models.deletion
import app_movil_mantenimiento_api.models


def populate_folios(apps, schema_editor):
    Ticket = apps.get_model('app_movil_mantenimiento_api', 'Ticket')
    Notification = apps.get_model('app_movil_mantenimiento_api', 'Notificacion')
    Counter = apps.get_model('app_movil_mantenimiento_api', 'TicketCounter')
    alias = schema_editor.connection.alias
    records = list(Ticket.objects.using(alias).order_by('id_ticket').values('id_ticket', 'numero_ticket', 'fecha_creacion'))
    used = set()
    assigned = {}
    highest = {}
    # Preserve every valid existing folio before allocating missing legacy values.
    for record in records:
        folio = record['numero_ticket']
        if isinstance(folio, str) and re.fullmatch(r'MANT-[0-9]{9}', folio):
            try:
                date = datetime.strptime(folio[5:11], '%y%m%d').date()
            except ValueError:
                continue
            if folio not in used:
                assigned[record['id_ticket']] = folio
                used.add(folio)
                highest[date] = max(highest.get(date, 0), int(folio[-3:]))
    for record in records:
        old_id = record['id_ticket']
        if old_id not in assigned:
            date = record['fecha_creacion'].date()
            counter = Counter.objects.using(alias).filter(fecha=date).first()
            number = max(highest.get(date, 0), counter.ultimo if counter else 0) + 1
            if number > 999:
                raise RuntimeError(f'No hay folios disponibles para {date}; la migración se detuvo sin eliminar identificadores.')
            folio = f'MANT-{date:%y%m%d}{number:03d}'
            assigned[old_id] = folio
            used.add(folio)
            highest[date] = number
    # All mappings are validated before changing either relationship.
    for old_id, folio in assigned.items():
        Ticket.objects.using(alias).filter(id_ticket=old_id).update(folio_nuevo=folio)
        Notification.objects.using(alias).filter(ticket_id=old_id).update(ticket_folio_id=folio)
    for date, number in highest.items():
        counter, _ = Counter.objects.using(alias).get_or_create(fecha=date)
        if counter.ultimo < number:
            counter.ultimo = number
            counter.save(using=alias, update_fields=['ultimo'])


class Migration(migrations.Migration):
    dependencies = [('app_movil_mantenimiento_api', '0010_ticket_cierre')]
    operations = [
        migrations.AddField(model_name='ticket', name='folio_nuevo', field=models.CharField(max_length=14, null=True, unique=True, editable=False)),
        migrations.AddField(model_name='notificacion', name='ticket_folio', field=models.ForeignKey(to='app_movil_mantenimiento_api.ticket', to_field='folio_nuevo', db_constraint=False, null=True, blank=True, related_name='+', on_delete=django.db.models.deletion.CASCADE)),
        migrations.RunPython(populate_folios),
        migrations.RemoveField(model_name='notificacion', name='ticket'),
        migrations.RemoveField(model_name='ticket', name='id_ticket'),
        migrations.AlterField(model_name='ticket', name='folio_nuevo', field=models.CharField(max_length=14, primary_key=True, editable=False, serialize=False)),
        migrations.RenameField(model_name='ticket', old_name='folio_nuevo', new_name='id_ticket'),
        migrations.RenameField(model_name='notificacion', old_name='ticket_folio', new_name='ticket'),
        migrations.AlterField(model_name='notificacion', name='ticket', field=models.ForeignKey(to='app_movil_mantenimiento_api.ticket', null=True, blank=True, related_name='notificaciones', on_delete=django.db.models.deletion.CASCADE)),
        migrations.RemoveField(model_name='ticket', name='numero_ticket'),
        migrations.SeparateDatabaseAndState(state_operations=[
            migrations.AlterField(model_name='ticket', name='id_ticket', field=models.CharField(max_length=14, primary_key=True, editable=False, default=app_movil_mantenimiento_api.models.default_ticket_id, serialize=False)),
        ]),
    ]
