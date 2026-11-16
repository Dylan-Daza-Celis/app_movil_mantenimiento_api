from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_movil_mantenimiento_api", "0008_notificacion")]
    operations = [migrations.CreateModel(
        name="TicketCounter",
        fields=[
            ("fecha", models.DateField(primary_key=True, serialize=False)),
            ("ultimo", models.PositiveIntegerField(default=0)),
        ],
    )]
