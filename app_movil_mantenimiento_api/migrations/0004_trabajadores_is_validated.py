from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_movil_mantenimiento_api", "0003_remove_administradores_clave_admin_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="trabajadores",
            name="is_validated",
            field=models.BooleanField(default=False),
        ),
    ]
