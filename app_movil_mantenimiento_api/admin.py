from django.contrib import admin
from django.utils.html import format_html
from app_movil_mantenimiento_api.models import *


@admin.register(Administradores)
class AdministradoresAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "id_admin", "telefono", "edad", "fecha_nacimiento")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")

@admin.register(Trabajadores)
class TrabajadoreeAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "id_trabajador", "telefono", "fecha_nacimiento", "biblioteca", "edad", "departamento")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")