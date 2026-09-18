from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from apps.accounts.permissions import IsSalesOrAdministration
from apps.recibos.models import Recibo
from apps.recibos.serializers import ReciboSerializer
from apps.recibos.servicios import anular_recibo, emitir_recibo


class ReciboViewSet(viewsets.ModelViewSet):
    http_method_names = ("get", "post", "head", "options")
    permission_classes = (IsSalesOrAdministration,)
    queryset = Recibo.objects.all()
    serializer_class = ReciboSerializer

    def get_queryset(self):
        return Recibo.objects.filter(pedido__proforma__vendedor=self.request.user).select_related(
            "pedido", "tipo_pago"
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            data = serializer.validated_data
            recibo = emitir_recibo(
                pedido_id=data["pedido"].pk,
                actor_id=request.user.pk,
                nombre_completo=data["nombre_completo"],
                monto_literal=data["monto_literal"],
                concepto=data["concepto"],
                tipo_pago_id=data["tipo_pago"].pk,
                pago_actual=data["pago_actual"],
                numero_cheque=data.get("numero_cheque", ""),
                banco=data.get("banco", ""),
            )
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response(self.get_serializer(recibo).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        recibo = self.get_object()
        try:
            recibo = anular_recibo(recibo_id=recibo.pk, actor_id=request.user.pk)
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response(self.get_serializer(recibo).data)
