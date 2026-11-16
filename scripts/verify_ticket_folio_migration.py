"""Verify populated migrations in a new disposable MariaDB database, never in application tables."""
import copy
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app_movil_mantenimiento_api.settings')
import django
django.setup()
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

name = 'test_folio_review_' + uuid.uuid4().hex[:12]
live = connections['default']
if live.vendor != 'mysql':
    raise RuntimeError('This check requires MariaDB/MySQL with permission to create a test database.')
with live.cursor() as cursor:
    cursor.execute('CREATE DATABASE `' + name + '` CHARACTER SET utf8mb4')
config = copy.deepcopy(live.settings_dict)
config['NAME'] = name
connections.databases['migration_review'] = config
review = connections['migration_review']
try:
    with review.cursor() as cursor:
        cursor.execute('SELECT DATABASE()')
        assert cursor.fetchone()[0] == name
    executor = MigrationExecutor(review)
    old_target = [('app_movil_mantenimiento_api', '0010_ticket_cierre')]
    executor.migrate(old_target)
    state = executor.loader.project_state(old_target).apps
    User = state.get_model('auth', 'User')
    Ticket = state.get_model('app_movil_mantenimiento_api', 'Ticket')
    Note = state.get_model('app_movil_mantenimiento_api', 'Notificacion')
    user = User.objects.using('migration_review').create(username='migration-check', password='!')
    payload = dict(usuario_id=user.pk, inventario='0123456789', marca='Marca', equipo={'value': '1'}, edificio='Central', area='Sala', descripcion='Migration test', problema={'value': 'No enciende'})
    folio = f'MANT-{timezone.localdate():%y%m%d}005'
    first = Ticket.objects.using('migration_review').create(numero_ticket=folio, **payload)
    second = Ticket.objects.using('migration_review').create(numero_ticket=None, **payload)
    Note.objects.using('migration_review').create(destinatario_id=user.pk, ticket_id=first.pk, tipo='ticket_nuevo', mensaje='First')
    Note.objects.using('migration_review').create(destinatario_id=user.pk, ticket_id=second.pk, tipo='ticket_nuevo', mensaje='Second')
    Note.objects.using('migration_review').create(destinatario_id=user.pk, tipo='usuario_validado', mensaje='Unrelated')
    executor = MigrationExecutor(review)
    target = [('app_movil_mantenimiento_api', '0011_ticket_folio_primary_key')]
    executor.migrate(target)
    state = executor.loader.project_state(target).apps
    Ticket = state.get_model('app_movil_mantenimiento_api', 'Ticket')
    Note = state.get_model('app_movil_mantenimiento_api', 'Notificacion')
    rows = list(Ticket.objects.using('migration_review').values_list('id_ticket', flat=True))
    assert len(rows) == 2 and len(set(rows)) == 2 and folio in rows
    assert all(value.startswith('MANT-') for value in rows)
    assert Note.objects.using('migration_review').get(mensaje='First').ticket_id == folio
    assert Note.objects.using('migration_review').get(mensaje='Second').ticket_id in rows
    assert Note.objects.using('migration_review').get(mensaje='Unrelated').ticket_id is None
    with review.cursor() as cursor:
        columns = [column.name for column in review.introspection.get_table_description(cursor, Ticket._meta.db_table)]
        constraints = review.introspection.get_constraints(cursor, Ticket._meta.db_table)
        note_constraints = review.introspection.get_constraints(cursor, Note._meta.db_table)
    assert 'numero_ticket' not in columns and 'id' not in columns
    assert any(c['primary_key'] and c['columns'] == ['id_ticket'] for c in constraints.values())
    assert any(c['foreign_key'] == (Ticket._meta.db_table, 'id_ticket') for c in note_constraints.values())
    Ticket.objects.using('migration_review').get(pk=folio).delete()
    assert Note.objects.using('migration_review').count() == 2
    print('OK: existing and missing folios, primary key, notification relationships and cascade deletion.')
finally:
    review.close()
    with live.cursor() as cursor:
        cursor.execute('DROP DATABASE `' + name + '`')
