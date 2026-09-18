from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsSalesOrAdministration
from apps.proformas.models import Proforma
from apps.proformas.serializers import ProformaSerializer
from apps.proformas.servicios import enviar_proforma


class ProformaViewSet(viewsets.ModelViewSet):
    permission_classes = (IsSalesOrAdministration,)
    queryset = Proforma.objects.all()
    serializer_class = ProformaSerializer

    def get_queryset(self):
        return Proforma.objects.filter(vendedor=self.request.user).order_by("-id")

    def perform_create(self, serializer):
        serializer.save(vendedor=self.request.user, creado_por=self.request.user)

    @action(detail=True, methods=("post",))
    def submit(self, request, pk=None):
        try:
            proforma = enviar_proforma(int(pk), request.user.id)
        except ValidationError as error:
            return Response({"detail": error.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(proforma).data)
