from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views.bootstrap import VersionView
from app_movil_mantenimiento_api.views import auth
from app_movil_mantenimiento_api.views import users, trabajadores, ticket, notificaciones


urlpatterns = [
    #Create Admin User
        path('admin/', users.AdminView.as_view()),
    #Create Trabajador User
        path('trabajador/validar/', trabajadores.ValidarTrabajadorView.as_view()),
        path('trabajador/', trabajadores.TrabajadoresView.as_view()),
    #Tickets
        path('ticket/', ticket.TicketView.as_view()),
        path('lista-tickets/', ticket.TicketsAll.as_view()),
    #Admin Data
        path('lista-admins/', users.AdminAll.as_view()),
    #Trabajador Data
        path('lista-trabajadores/', trabajadores.TrabajadoresAll.as_view()),
    #Total Users
        path('total-usuarios/', users.TotalUsers.as_view()),
        path('cambiar-password/', users.ChangePasswordView.as_view()),
        path('notificaciones/', notificaciones.NotificacionesView.as_view()),
    #Login and Logout
        path('login/', auth.CustomAuthToken.as_view()),
        path('logout/', auth.Logout.as_view()), 
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
