from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from apps.accounts.permissions import IsSalesOrAdministration
from apps.notas_entrega.models import NotaEntrega
from apps.notas_entrega.serializers import NotaEntregaSerializer
from apps.notas_entrega.servicios import emitir_nota_entrega


class NotaEntregaViewSet(viewsets.ModelViewSet):
    http_method_names = ("get", "post", "head", "options")
    permission_classes = (IsSalesOrAdministration,)
    queryset = NotaEntrega.objects.all()
    serializer_class = NotaEntregaSerializer

    def get_queryset(self):
        return NotaEntrega.objects.filter(vendedor=self.request.user).select_related(
            "pedido", "vendedor"
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            note = emitir_nota_entrega(
                pedido_id=serializer.validated_data["pedido"].pk,
                vendedor_id=request.user.pk,
                actor_id=request.user.pk,
            )
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response(self.get_serializer(note).data, status=status.HTTP_201_CREATED)
