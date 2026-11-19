from datetime import datetime, timedelta, timezone as datetime_timezone

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.db import close_old_connections, connections
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.conf import settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import Administradores, Notificacion, Ticket, TicketCounter, Trabajadores


PASSWORD = "Valid!Maintenance-2026"


class ApplicationFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = self.make_user("admin", "administrador")
        self.worker = self.make_user("worker", "trabajador", True)
        self.pending = self.make_user("pending", "trabajador", False)
        self.other = self.make_user("other", "trabajador", True)
        self.payload = {
            "inventario": "0123456789", "marca": "Marca", "edificio": "Central",
            "area": "Sala", "descripcion": "Equipo sin encender",
            "equipo": {"value": "1", "descripcion": None},
            "problema": {"value": "No enciende", "descripcion": None},
            "sistema_operativo": "Windows 11",
        }

    def make_user(self, name, role, validated=False):
        user = User.objects.create_user(username=f"{name}@example.com", email=f"{name}@example.com", password=PASSWORD, first_name=name, last_name="Apellido")
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
        model = Administradores if role == "administrador" else Trabajadores
        kwargs = {} if role == "administrador" else {"is_validated": validated}
        model.objects.create(user=user, **kwargs)
        return user

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def new_ticket(self, user=None):
        self.as_user(user or self.worker)
        result = self.client.post("/ticket/", self.payload, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        return Ticket.objects.get(pk=result.data["ticket_created_id"])

    def profile_payload(self, role="trabajador"):
        return {
            "rol": role, "first_name": "Persona", "last_name": "Nueva",
            "email": "new@example.com", "password": PASSWORD, "confirmar_password": PASSWORD,
            "telefono": "2221234567", "edad": 30, "fecha_nacimiento": "1996-01-01",
            "id_admin": "A1", "id_trabajador": "T1", "departamento": "Servicios", "biblioteca": "Central",
        }

    def test_public_admin_registration_is_forbidden(self):
        response = self.client.post("/admin/", self.profile_payload("administrador"), format="json")
        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_public_worker_cannot_choose_admin_role(self):
        response = self.client.post("/trabajador/", self.profile_payload("administrador"), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_public_registration_login_pending_then_validation_and_ticket(self):
        response = self.client.post("/trabajador/", self.profile_payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="new@example.com")
        self.assertFalse(Trabajadores.objects.get(user=user).is_validated)
        self.assertTrue(Notificacion.objects.filter(destinatario=self.admin, tipo="usuario_pendiente").exists())
        response = self.client.post("/login/", {"username": user.username, "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.data)
        self.assertFalse(response.data["is_validated"])
        self.as_user(user)
        self.assertEqual(self.client.post("/ticket/", self.payload, format="json").status_code, 403)
        self.as_user(self.admin)
        response = self.client.put("/trabajador/validar/", {"id": Trabajadores.objects.get(user=user).id, "is_validated": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.new_ticket(user)

    def test_admin_can_register_admin(self):
        self.as_user(self.admin)
        response = self.client.post("/admin/", self.profile_payload("administrador"), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(User.objects.get(email="new@example.com").groups.filter(name="administrador").exists())

    def test_worker_cannot_manage_admins_or_list_personal_data(self):
        self.as_user(self.worker)
        for url in ("/lista-admins/", "/lista-trabajadores/", "/total-usuarios/", "/admin/?id=1"):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.assertEqual(self.client.put("/admin/", {"id": 1}, format="json").status_code, 403)
        self.assertEqual(self.client.delete("/admin/?id=1").status_code, 403)

    def test_worker_cannot_read_other_profile(self):
        self.as_user(self.worker)
        profile = Trabajadores.objects.get(user=self.other)
        self.assertEqual(self.client.get(f"/trabajador/?id={profile.id}").status_code, 403)

    def test_worker_can_update_own_profile(self):
        self.as_user(self.worker)
        payload = self.profile_payload()
        payload["id"] = Trabajadores.objects.get(user=self.worker).id
        response = self.client.put("/trabajador/", payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def test_invalid_registration_is_atomic(self):
        payload = self.profile_payload()
        del payload["biblioteca"]
        self.assertEqual(self.client.post("/trabajador/", payload, format="json").status_code, 400)
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_weak_password_registration_is_rejected(self):
        payload = self.profile_payload()
        payload.update(password="123456", confirmar_password="123456")
        self.assertEqual(self.client.post("/trabajador/", payload, format="json").status_code, 400)

    def test_invalid_validation_boolean_rejected(self):
        self.as_user(self.admin)
        response = self.client.put("/trabajador/validar/", {"id": Trabajadores.objects.get(user=self.pending).id, "is_validated": "false"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_pending_cannot_list_tickets(self):
        self.as_user(self.pending)
        self.assertEqual(self.client.get("/lista-tickets/").status_code, 403)

    def test_ticket_owner_is_always_authenticated_user(self):
        self.as_user(self.worker)
        response = self.client.post("/ticket/", {**self.payload, "usuario": self.other.id}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Ticket.objects.get(pk=response.data["ticket_created_id"]).usuario_id, self.worker.id)

    def test_ticket_data_stays_private(self):
        ticket = self.new_ticket()
        self.as_user(self.other)
        self.assertEqual(self.client.get(f"/ticket/?id={ticket.pk}").status_code, 403)
        self.assertEqual(self.client.get("/lista-tickets/").data, [])
        self.assertEqual(self.client.put("/ticket/", {"id_ticket": ticket.pk, "marca": "Otra"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/ticket/?id={ticket.pk}").status_code, 403)

    def test_worker_cannot_change_tracking(self):
        ticket = self.new_ticket()
        response = self.client.put("/ticket/", {"id_ticket": ticket.pk, "estatus": "resuelto"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_admin_can_respond_resolve_and_list_ticket(self):
        ticket = self.new_ticket()
        self.as_user(self.admin)
        response = self.client.put("/ticket/", {"id_ticket": ticket.pk, "respuesta_usuario": "En revisión"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.put("/ticket/", {"id_ticket": ticket.pk, "estatus": "resuelto", "descripcion_reparacion": "Se cambió la fuente", "solucionado_por": "Ana Pérez y Luis López"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(self.client.get("/lista-tickets/").data), 0)
        self.assertEqual(self.client.get('/historial-tickets/').data['count'], 1)
        self.as_user(self.worker)
        self.assertEqual(self.client.delete(f"/ticket/?id={ticket.pk}").status_code, 403)
        self.assertTrue(Notificacion.objects.filter(destinatario=self.worker, tipo="mensaje_ticket").exists())

    def test_resolving_requires_repair_description(self):
        ticket = self.new_ticket()
        self.as_user(self.admin)
        self.assertEqual(self.client.put("/ticket/", {"id_ticket": ticket.pk, "estatus": "resuelto"}, format="json").status_code, 400)
        ticket.refresh_from_db()
        self.assertEqual(ticket.estatus, "pendiente")

    def test_tracking_does_not_overwrite_manual_priority(self):
        ticket = self.new_ticket()
        ticket.prioridad = "baja"
        ticket.save()
        self.as_user(self.admin)
        self.assertEqual(self.client.put("/ticket/", {"id_ticket": ticket.pk, "respuesta_usuario": "Mensaje"}, format="json").status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.prioridad, "baja")

    def test_resolving_requires_valid_solver_names_without_saving_partial_changes(self):
        ticket = self.new_ticket()
        self.as_user(self.admin)
        for names in (None, '', '   ', 'a' * 501, ['Ana', 'Luis']):
            with self.subTest(names=names):
                response = self.client.put('/ticket/', {
                    'id_ticket': ticket.pk, 'estatus': 'resuelto',
                    'descripcion_reparacion': 'Equipo reparado', 'solucionado_por': names,
                }, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('solucionado_por', response.data)
                ticket.refresh_from_db()
                self.assertEqual(ticket.estatus, 'pendiente')
                self.assertIsNone(ticket.fecha_finalizacion)
                self.assertIsNone(ticket.descripcion_reparacion)

    def test_worker_cannot_set_solver_names(self):
        ticket = self.new_ticket()
        response = self.client.put('/ticket/', {'id_ticket': ticket.pk, 'solucionado_por': 'Ana'}, format='json')
        self.assertEqual(response.status_code, 403)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.solucionado_por)

    def test_malformed_tickets_return_validation_errors(self):
        self.as_user(self.worker)
        for changes in ({"equipo": {"value": []}}, {"problema": {}}, {"problema": {"value": []}}, {"marca": "x" * 61}, {"descripcion": " "}, {"equipo": None}):
            with self.subTest(changes=changes):
                response = self.client.post("/ticket/", {**self.payload, **changes}, format="json")
                self.assertEqual(response.status_code, 400, response.data)

    def test_invalid_status_rejected(self):
        ticket = self.new_ticket()
        self.as_user(self.admin)
        self.assertEqual(self.client.put("/ticket/", {"id_ticket": ticket.pk, "estatus": "inventado"}, format="json").status_code, 400)

    def test_partial_update_checks_existing_problem_and_system(self):
        ticket = self.new_ticket()
        response = self.client.put("/ticket/", {"id_ticket": ticket.pk, "equipo": {"value": "4", "descripcion": None}}, format="json")
        self.assertEqual(response.status_code, 400)
        ticket.refresh_from_db()
        self.assertEqual(ticket.equipo["value"], "1")

    def test_folios_not_reused_after_deletion(self):
        first = self.new_ticket()
        second = self.new_ticket()
        first.delete()
        third = self.new_ticket()
        self.assertNotEqual(second.numero_ticket, third.numero_ticket)
        self.assertEqual(int(third.numero_ticket[-3:]), 3)
        third.delete()
        fourth = self.new_ticket()
        self.assertEqual(int(fourth.numero_ticket[-3:]), 4)

    def test_ticket_folio_uses_puebla_date_and_resets_at_local_midnight(self):
        from unittest.mock import patch
        self.assertEqual(settings.TIME_ZONE, 'America/Mexico_City')
        with timezone.override('America/Mexico_City'):
            with patch('app_movil_mantenimiento_api.ticket_numbers.timezone.now', return_value=datetime(2026,11,17,0,30,tzinfo=datetime_timezone.utc)):
                first = self.new_ticket()
            with patch('app_movil_mantenimiento_api.ticket_numbers.timezone.now', return_value=datetime(2026,11,17,5,59,tzinfo=datetime_timezone.utc)):
                second = self.new_ticket()
            with patch('app_movil_mantenimiento_api.ticket_numbers.timezone.now', return_value=datetime(2026,11,17,6,0,tzinfo=datetime_timezone.utc)):
                third = self.new_ticket()
        self.assertEqual(first.pk, 'MANT-261116001')
        self.assertEqual(second.pk, 'MANT-261116002')
        self.assertEqual(third.pk, 'MANT-261117001')

    def test_counter_recovers_existing_legacy_folios(self):
        first = self.new_ticket()
        Notificacion.objects.filter(ticket=first).delete()
        Ticket.objects.filter(pk=first.pk).update(id_ticket=first.id_ticket[:-3] + "020")
        TicketCounter.objects.all().delete()
        self.assertEqual(int(self.new_ticket().numero_ticket[-3:]), 21)

    def test_daily_limit_returns_400_without_partial_records(self):
        ticket = self.new_ticket()
        TicketCounter.objects.update(ultimo=999)
        self.as_user(self.worker)
        self.assertEqual(self.client.post("/ticket/", self.payload, format="json").status_code, 400)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_password_rotation_keeps_current_session_and_revokes_old_token(self):
        old = Token.objects.create(user=self.worker).key
        self.as_user(self.worker)
        response = self.client.post("/cambiar-password/", {
            "role": "trabajador", "target_id": Trabajadores.objects.get(user=self.worker).id,
            "current_password": PASSWORD, "new_password": "Replacement!Maintenance2026", "confirm_password": "Replacement!Maintenance2026",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("token", response.data)
        self.assertFalse(Token.objects.filter(key=old).exists())
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["token"])
        self.assertEqual(client.get("/me/").status_code, 200)

    def test_admin_own_password_requires_current_password(self):
        self.as_user(self.admin)
        response = self.client.post("/cambiar-password/", {
            "role": "administrador", "target_id": Administradores.objects.get(user=self.admin).id,
            "new_password": PASSWORD, "confirm_password": PASSWORD,
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_worker_cannot_reset_another_password(self):
        self.as_user(self.worker)
        response = self.client.post("/cambiar-password/", {
            "role": "trabajador", "target_id": Trabajadores.objects.get(user=self.other).id,
            "new_password": PASSWORD, "confirm_password": PASSWORD,
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_admin_session_uses_profile_id_not_user_id(self):
        another = self.make_user("another-admin", "administrador")
        response = self.client.post("/login/", {"username": another.username, "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], Administradores.objects.get(user=another).id)
        self.assertEqual(response.data["user"]["id"], another.id)

    def test_user_without_role_gets_403_not_server_error(self):
        user = User.objects.create_user(username="nogroup", password=PASSWORD)
        self.assertEqual(self.client.post("/login/", {"username": user.username, "password": PASSWORD}).status_code, 403)

    def test_logout_revokes_token_and_is_idempotent_for_session_auth(self):
        token = Token.objects.create(user=self.worker)
        self.as_user(self.worker)
        self.assertEqual(self.client.post("/logout/").status_code, 200)
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())
        self.assertEqual(self.client.post("/logout/").status_code, 200)

    def test_invalid_identifier_returns_400(self):
        self.as_user(self.admin)
        self.assertEqual(self.client.get("/ticket/?id=invalid").status_code, 400)

    def test_ticket_identifier_is_only_the_unique_folio(self):
        ticket = self.new_ticket()
        self.assertIsInstance(ticket.pk, str)
        self.assertRegex(ticket.pk, r'^MANT-[0-9]{9}$')
        self.assertEqual(ticket.numero_ticket, ticket.pk)
        self.assertNotIn('numero_ticket', [field.name for field in Ticket._meta.fields])
        response = self.client.get('/ticket/', {'id': ticket.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id_ticket'], response.data['numero_ticket'])
        self.assertEqual(self.client.get('/ticket/?id=1').status_code, 400)
        self.assertEqual(self.client.delete('/ticket/?id=1').status_code, 400)

    def test_login_throttle(self):
        for _ in range(10):
            self.client.post("/login/", {"username": "missing", "password": "wrong"})
        self.assertEqual(self.client.post("/login/", {"username": "missing", "password": "wrong"}).status_code, 429)

    def test_expired_token_is_rejected_and_login_renews_it(self):
        token = Token.objects.create(user=self.worker)
        Token.objects.filter(pk=token.pk).update(created=timezone.now() - timedelta(seconds=settings.AUTH_TOKEN_MAX_AGE_SECONDS + 1))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + token.key)
        self.assertIn(client.get("/me/").status_code, (401, 403))
        response = self.client.post("/login/", {"username": self.worker.username, "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["token"], token.key)

    def test_notifications_summary_counts_more_than_fifty(self):
        Notificacion.objects.bulk_create([
            Notificacion(destinatario=self.worker, tipo="mensaje_ticket", mensaje="Mensaje") for _ in range(60)
        ])
        self.as_user(self.worker)
        self.assertEqual(len(self.client.get("/notificaciones/").data), 50)
        self.assertEqual(self.client.get("/notificaciones/?summary=true").data["unread_count"], 60)

    def test_pagination_keeps_global_priority_order_and_summary(self):
        for _ in range(11):
            self.new_ticket()
        urgent = self.new_ticket()
        urgent.prioridad = "critica"
        urgent.save()
        self.as_user(self.admin)
        response = self.client.get("/lista-tickets/?page=1")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 12)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertEqual(response.data["results"][0]["id_ticket"], urgent.pk)
        self.assertEqual(response.data["summary"]["pending_count"], 12)
        self.assertEqual(response.data["summary"]["priority_counts"]["critica"], 1)
        self.assertEqual(response.data["summary"]["priority_counts"]["alta"], 11)
        response = self.client.get("/lista-tickets/?page=2")
        self.assertEqual(len(response.data["results"]), 2)

    def test_worker_pagination_never_includes_other_users(self):
        self.new_ticket(self.other)
        self.new_ticket(self.worker)
        self.as_user(self.worker)
        response = self.client.get("/lista-tickets/?page=1")
        self.assertEqual(response.data["count"], 1)
        self.assertNotIn("prioridad", response.data["results"][0])
        self.assertEqual(response.data["summary"]["priority_counts"], {})

    def test_filters_combine_and_preserve_global_counts(self):
        Trabajadores.objects.filter(user=self.worker).update(biblioteca="Central")
        Trabajadores.objects.filter(user=self.other).update(biblioteca="Norte")
        first = self.new_ticket(self.worker)
        second = self.new_ticket(self.other)
        second.prioridad = "baja"
        second.save()
        self.as_user(self.admin)
        response = self.client.get("/lista-tickets/", {"page": 1, "prioridad": "alta", "biblioteca": "Central"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id_ticket"], first.pk)
        self.assertEqual(response.data["summary"]["pending_count"], 2)
        self.assertEqual(response.data["filters"]["bibliotecas"], ["Central", "Norte"])
        self.assertEqual(self.client.get("/lista-tickets/", {"page": 1, "prioridad": "baja", "biblioteca": "Central"}).data["count"], 0)

    def test_library_filter_preserves_worker_privacy(self):
        Trabajadores.objects.filter(user=self.other).update(biblioteca="Privada")
        self.new_ticket(self.other)
        self.as_user(self.worker)
        response = self.client.get("/lista-tickets/", {"page": 1, "biblioteca": "Privada"})
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["filters"]["bibliotecas"], [])
        self.assertEqual(self.client.get("/lista-tickets/?page=1&prioridad=alta").status_code, 403)

    def test_finalized_ticket_moves_to_history_with_full_details(self):
        ticket = self.new_ticket()
        self.as_user(self.admin)
        response = self.client.put('/ticket/', {'id_ticket': ticket.pk, 'estatus': 'resuelto', 'descripcion_reparacion': 'Se reemplazó la fuente', 'solucionado_por': '  Ana Pérez y Luis López  '}, format='json')
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.fecha_finalizacion)
        self.assertEqual(ticket.finalizado_por_id, self.admin.id)
        self.assertEqual(self.client.get('/lista-tickets/?page=1').data['count'], 0)
        result = self.client.get('/historial-tickets/').data
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['results'][0]['descripcion_reparacion'], 'Se reemplazó la fuente')
        self.assertEqual(result['results'][0]['solucionado_por'], 'Ana Pérez y Luis López')
        self.assertEqual(self.client.get('/ticket/', {'id': ticket.pk}).data['solucionado_por'], 'Ana Pérez y Luis López')
        self.assertEqual(result['stats']['total'], 1)
        original_date = ticket.fecha_finalizacion
        self.assertEqual(self.client.put('/ticket/', {'id_ticket': ticket.pk, 'respuesta_usuario': 'Otro mensaje'}, format='json').status_code, 409)
        ticket.refresh_from_db()
        self.assertEqual(ticket.fecha_finalizacion, original_date)

    def test_history_month_and_year_use_puebla_time_and_annual_statistics(self):
        ticket = self.new_ticket()
        Ticket.objects.filter(pk=ticket.pk).update(
            estatus='resuelto', fecha_creacion=datetime(2026,12,31,0,tzinfo=datetime_timezone.utc),
            fecha_finalizacion=datetime(2027,1,1,2,tzinfo=datetime_timezone.utc))
        self.as_user(self.admin)
        result = self.client.get('/historial-tickets/?year=2026&month=12').data
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['periods'], [{'year': 2026, 'month': 12, 'total': 1}])
        self.assertEqual(result['stats']['average_hours'], 26)
        self.assertEqual(result['stats']['monthly'][11]['total'], 1)
        self.assertEqual(result['stats']['priorities']['alta'], 1)
        result = self.client.get('/historial-tickets/?year=2026&month=11').data
        self.assertEqual(result['count'], 0)
        self.assertEqual(result['stats']['total'], 1)

    def test_old_history_dates_are_estimated_and_not_in_average(self):
        ticket = self.new_ticket()
        Ticket.objects.filter(pk=ticket.pk).update(estatus='resuelto', fecha_modificacion=timezone.now())
        self.as_user(self.admin)
        result = self.client.get('/historial-tickets/').data
        self.assertTrue(result['results'][0]['cierre_estimado'])
        self.assertIsNone(result['stats']['average_hours'])
        self.assertEqual(result['stats']['measured_count'], 0)

    def test_worker_history_is_private_and_has_no_admin_metrics(self):
        ticket = self.new_ticket(self.other)
        Ticket.objects.filter(pk=ticket.pk).update(estatus='resuelto', fecha_finalizacion=timezone.now())
        self.as_user(self.worker)
        result = self.client.get('/historial-tickets/').data
        self.assertEqual(result['count'], 0)
        self.assertEqual(result['periods'], [])
        self.assertIsNone(result['stats'])
        self.as_user(self.other)
        self.assertEqual(self.client.get('/historial-tickets/').data['count'], 1)

    def test_worker_history_is_limited_to_one_calendar_month_even_with_filters(self):
        from unittest.mock import patch
        end = datetime(2026, 3, 31, 12, tzinfo=datetime_timezone.utc)
        boundary = datetime(2026, 2, 28, 12, tzinfo=datetime_timezone.utc)
        expected = []
        for closed_at in (boundary, boundary + timedelta(seconds=1), end):
            ticket = self.new_ticket()
            Ticket.objects.filter(pk=ticket.pk).update(estatus='resuelto', fecha_finalizacion=closed_at, descripcion_reparacion='Equipo reparado')
            expected.append(ticket.pk)
        for closed_at in (boundary - timedelta(seconds=1), datetime(2026, 1, 15, tzinfo=datetime_timezone.utc), end + timedelta(seconds=1)):
            ticket = self.new_ticket()
            Ticket.objects.filter(pk=ticket.pk).update(estatus='resuelto', fecha_finalizacion=closed_at)
        other = self.new_ticket(self.other)
        Ticket.objects.filter(pk=other.pk).update(estatus='resuelto', fecha_finalizacion=end)
        self.as_user(self.worker)
        with patch('app_movil_mantenimiento_api.views.historial.timezone.now', return_value=end):
            response = self.client.get('/historial-tickets/?year=1999&month=1&page=100')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual({row['id_ticket'] for row in response.data['results']}, set(expected))
        self.assertEqual(response.data['periods'], [])
        self.assertIsNone(response.data['stats'])
        self.assertIsNone(response.data['next'])
        self.as_user(self.admin)
        response = self.client.get('/historial-tickets/?year=2026&month=1')
        self.assertEqual(response.data['count'], 1)

    def test_worker_history_shows_all_recent_results_without_pagination(self):
        for _ in range(12):
            ticket = self.new_ticket()
            Ticket.objects.filter(pk=ticket.pk).update(estatus='resuelto', fecha_finalizacion=timezone.now())
        result = self.client.get('/historial-tickets/').data
        self.assertEqual(result['count'], 12)
        self.assertEqual(len(result['results']), 12)
        self.assertIsNone(result['next'])

    def test_history_rejects_invalid_periods_and_pending_accounts(self):
        self.as_user(self.admin)
        for query in ('year=abc', 'year=0', 'month=13', 'month=hello'):
            self.assertEqual(self.client.get('/historial-tickets/?'+query).status_code, 400)
        self.as_user(self.pending)
        self.assertEqual(self.client.get('/historial-tickets/').status_code, 403)

    def test_requester_snapshot_survives_profile_changes(self):
        Trabajadores.objects.filter(user=self.worker).update(biblioteca='Biblioteca original')
        ticket = self.new_ticket()
        self.worker.first_name = 'Otro nombre'
        self.worker.save()
        Trabajadores.objects.filter(user=self.worker).update(biblioteca='Otra biblioteca')
        self.as_user(self.admin)
        result = self.client.get('/ticket/?id='+str(ticket.pk)).data
        self.assertEqual(result['solicitante']['biblioteca'], 'Biblioteca original')
        self.assertEqual(result['solicitante']['nombre'], 'worker Apellido')

    def test_two_high_priority_tickets_from_same_user_count_as_two(self):
        first = self.new_ticket(self.worker)
        self.new_ticket(self.worker)
        self.as_user(self.admin)
        response = self.client.get("/lista-tickets/?page=1")
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["summary"]["pending_count"], 2)
        self.assertEqual(response.data["summary"]["priority_counts"]["alta"], 2)
        first.estatus = Ticket.ESTATUS_RESUELTO
        first.save()
        response = self.client.get("/lista-tickets/?page=1")
        self.assertEqual(response.data["summary"]["pending_count"], 1)
        self.assertEqual(response.data["summary"]["priority_counts"]["alta"], 1)


class ConcurrentTicketTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_simultaneous_first_requests_receive_distinct_folios(self):
        user = User.objects.create_user(username="concurrent@example.com", password=PASSWORD)
        group, _ = Group.objects.get_or_create(name="trabajador")
        user.groups.add(group)
        Trabajadores.objects.create(user=user, is_validated=True)
        barrier = Barrier(4)

        def create_ticket(_):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(user=user)
                barrier.wait(timeout=10)
                response = client.post("/ticket/", {
                    "inventario": "0123456789", "marca": "Marca", "edificio": "Central",
                    "area": "Sala", "descripcion": "No enciende",
                    "equipo": {"value": "1", "descripcion": None},
                    "problema": {"value": "No enciende", "descripcion": None},
                    "sistema_operativo": "Windows 11",
                }, format="json")
                return response.status_code, response.data
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(create_ticket, range(4)))
        self.assertTrue(all(code == 201 for code, _ in results), results)
        self.assertEqual(len({data["numero_ticket"] for _, data in results}), 4)
        self.assertEqual(Ticket.objects.count(), 4)


class UtilityCompatibilityTests(SimpleTestCase):
    def test_new_ciphertext_is_randomized_and_roundtrips(self):
        from .cypher_utils import CypherUtils
        first = CypherUtils.encrypt1(b"original", b"password")
        second = CypherUtils.encrypt1(b"original", b"password")
        self.assertNotEqual(first, second)
        self.assertEqual(CypherUtils.decrypt1(first, b"password"), b"original")

    def test_legacy_ciphertext_is_still_readable(self):
        from .cypher_utils import CypherUtils
        legacy = CypherUtils.cipherFernet(b"password").encrypt(b"original")
        self.assertEqual(CypherUtils.decrypt1(legacy, b"password"), b"original")

    def test_external_image_check_does_not_request_untrusted_hosts(self):
        from unittest.mock import patch
        from .data_utils import DataUtils
        with patch("app_movil_mantenimiento_api.data_utils.requests.head") as head:
            self.assertFalse(DataUtils.is_url_image("http://127.0.0.1/private"))
            self.assertFalse(DataUtils.is_url_image("https://untrusted.example/private"))
            head.assert_not_called()
