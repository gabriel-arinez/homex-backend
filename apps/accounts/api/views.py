from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.serializers import IdentidadActualSerializer
from apps.core.permissions import capacidades_usuario
from apps.proformas.models import RegistroProcedenciaImportacion


class IdentidadActualView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        responses={
            200: IdentidadActualSerializer,
            401: OpenApiResponse(description="Autenticación requerida."),
        },
    )
    def get(self, request):
        user = request.user

        entorno_eval = bool(
            getattr(settings, "HOMEX_ENTORNO_EVALUACION", False)
            or RegistroProcedenciaImportacion.objects.filter(perfil="ESCENARIO").exists()
        )
        serializer = IdentidadActualSerializer(
            {
                "id": user.pk,
                "username": user.get_username(),
                "display_name": user.get_full_name().strip() or user.get_username(),
                "capabilities": capacidades_usuario(user),
                "entorno_evaluacion": entorno_eval,
            }
        )

        return Response(serializer.data)
