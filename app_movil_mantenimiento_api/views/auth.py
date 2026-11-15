from django.db.models import *
from app_movil_mantenimiento_api.serializers import *
from app_movil_mantenimiento_api.models import *
from rest_framework import permissions
from rest_framework import generics
from rest_framework import status
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework.response import Response

class CustomAuthToken(ObtainAuthToken):

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data,
                                        context={'request': request})

        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        if user.is_active:
            # Obtener perfil y roles del usuario
            roles = user.groups.all()
            role_names = []
            # Verifico si el usuario tiene un perfil asociado
            for role in roles:
                role_names.append(role.name)

            #Si solo es un rol especifico asignamos el elemento 0
            role_names = role_names[0]
            
            #Esta función genera la clave dinámica (token) para iniciar sesión
            token, created = Token.objects.get_or_create(user=user)
            
            #Verificar que tipo de usuario quiere iniciar sesión
            
            if role_names == 'trabajador':
                alumno = Trabajadores.objects.filter(user=user).first()
                alumno = TrabajadoresSerializer(alumno).data
                alumno["token"] = token.key
                alumno["rol"] = "trabajador"
                return Response(alumno,200)
            if role_names == 'administrador':
                user = UserSerializer(user, many=False).data
                user['token'] = token.key
                user["rol"] = "administrador"
                return Response(user,200)
            else:
                return Response({"details":"Forbidden"},403)
                pass
            
        return Response({}, status=status.HTTP_403_FORBIDDEN)


class Logout(generics.GenericAPIView):

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):

        user = request.user
        if user.is_active:
            token = Token.objects.get(user=user)
            token.delete()

            return Response({'logout':True})


        return Response({'logout': False})