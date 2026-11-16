# backend
backend para front de proyectos

## Identificador de reportes

Desde la migración `0011_ticket_folio_primary_key`, la clave primaria de Ticket es `id_ticket`, de tipo texto y con formato `MANT-AAMMDDNNN`. No existe una clave numérica adicional. El campo `numero_ticket` de las respuestas de la API se conserva como alias del mismo folio para compatibilidad; no es otra columna de la base de datos.

Las consultas y bajas usan `?id=MANT-...`; las actualizaciones envían `id_ticket: "MANT-..."`. Los IDs de usuarios y de las notificaciones conservan sus tipos existentes.

La migración conserva los folios válidos, genera los que falten en reportes antiguos y reasigna las relaciones de notificaciones antes de retirar la clave numérica. Se debe aplicar sin escrituras concurrentes. Es una conversión irreversible: restaurar un respaldo requiere recuperar también el estado de migraciones correspondiente. Los respaldos locales de las tablas afectadas están excluidos de Git y del despliegue.

Para verificar la conversión con datos sintéticos, sin tocar los reportes de la aplicación: `python scripts/verify_ticket_folio_migration.py`. Requiere MariaDB/MySQL y permisos para crear y eliminar una base temporal.

## Historial de reportes

Aplicar `python manage.py migrate` antes de iniciar con estos cambios (migración `0010_ticket_cierre`).

- `/lista-tickets/` devuelve únicamente reportes activos.
- `/historial-tickets/?year=2026&month=11&page=1` devuelve reportes finalizados, paginados y agrupables por fecha de cierre en hora de Puebla. Año y mes son opcionales.
- Los administradores reciben estadísticas anuales. El historial del trabajador solo devuelve sus reportes finalizados entre el momento actual menos un mes calendario y el momento actual, sin paginación ni métricas. Los filtros `year`, `month` y `page` no amplían esa ventana. No se borran reportes antiguos; los administradores conservan el historial completo.
- Cada cierre nuevo guarda fecha y administrador responsable. Los reportes finalizados se consultan sin edición; su eliminación sigue requiriendo permisos.
- El promedio se calcula desde la creación hasta el cierre confirmado, en horas transcurridas. Excluye cierres antiguos estimados y duraciones inválidas.
- Los tickets antiguos usan la última modificación como fecha estimada de cierre (o la creación si no existe). El sistema no inventa fechas ni responsables anteriores.
- Los reportes nuevos conservan los datos del solicitante al registrar la solicitud; los antiguos mantienen el perfil disponible y se identifican en el modal.
