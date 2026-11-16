from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('app_movil_mantenimiento_api', '0009_ticketcounter'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='ticket', name='solicitante_snapshot', field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='ticket', name='fecha_finalizacion', field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name='ticket', name='finalizado_por', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tickets_finalizados', to=settings.AUTH_USER_MODEL)),
    ]
