from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('app_movil_mantenimiento_api', '0011_ticket_folio_primary_key')]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='solucionado_por',
            field=models.TextField(blank=True, max_length=500, null=True),
        ),
    ]
