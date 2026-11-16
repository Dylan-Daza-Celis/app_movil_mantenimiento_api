from getpass import getpass

from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from app_movil_mantenimiento_api.models import Administradores


class Command(BaseCommand):
    help = "Crea el primer administrador desde la consola del servidor."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--first-name", required=True)
        parser.add_argument("--last-name", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        if User.objects.filter(groups__name="administrador", is_active=True).exists():
            raise CommandError("Ya existe un administrador. Usa el registro autenticado de la aplicación.")
        email = options["email"].strip()
        user = User(username=email, email=email, first_name=options["first_name"], last_name=options["last_name"])
        if User.objects.filter(username__iexact=email).exists():
            raise CommandError("El correo ya está registrado.")
        try:
            validate_email(email)
            password = getpass("Contraseña: ")
            if password != getpass("Confirma la contraseña: "):
                raise CommandError("Las contraseñas no coinciden.")
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        user.set_password(password)
        user.save()
        group, _ = Group.objects.get_or_create(name="administrador")
        user.groups.add(group)
        Administradores.objects.create(user=user)
        self.stdout.write(self.style.SUCCESS("Administrador inicial creado."))
