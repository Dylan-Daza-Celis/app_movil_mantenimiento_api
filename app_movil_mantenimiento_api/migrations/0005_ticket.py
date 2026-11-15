from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app_movil_mantenimiento_api", "0004_trabajadores_is_validated"),
    ]

    operations = [
        migrations.CreateModel(
            name="Ticket",
            fields=[
                (
                    "id_ticket",
                    models.BigAutoField(primary_key=True, serialize=False),
                ),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("respuesta_usuario", models.TextField(blank=True, null=True)),
                (
                    "estatus",
                    models.CharField(
                        choices=[
                            ("pendiente", "Pendiente"),
                            ("en_proceso", "En proceso"),
                            ("resuelto", "Resuelto"),
                        ],
                        default="pendiente",
                        max_length=20,
                    ),
                ),
                ("prioridad", models.CharField(blank=True, max_length=20, null=True)),
                ("inventario", models.CharField(max_length=10)),
                ("marca", models.CharField(max_length=60)),
                ("equipo", models.JSONField(default=dict)),
                ("edificio", models.CharField(max_length=100)),
                ("area", models.CharField(max_length=100)),
                ("descripcion", models.TextField(max_length=1000)),
                ("fecha_respuesta", models.DateTimeField(blank=True, null=True)),
                ("sistema_operativo", models.CharField(blank=True, max_length=30, null=True)),
                ("problema", models.JSONField(default=dict)),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tickets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
