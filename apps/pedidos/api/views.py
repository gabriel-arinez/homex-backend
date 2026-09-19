from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalogo.models import ValorCatalogo
from apps.core.permissions import EsVendedor
from apps.notas_entrega.api.views import NotaEntregaSerializer
from apps.notas_entrega.services import emitir_nota
from apps.pedidos.models import Pedido
from apps.pedidos.services import cambiar_estado_pedido, cancelar_pedido
from apps.recibos.api.views import ReciboSerializer
from apps.recibos.services import emitir_recibo


class EmitirReciboSerializer(serializers.Serializer):
    nombre_completo = serializers.CharField(max_length=250)
    monto_en_letras = serializers.CharField()
    concepto = serializers.CharField()
    tipo_pago = serializers.PrimaryKeyRelatedField(queryset=ValorCatalogo.objects.all())
    numero_cheque = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    banco = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    pago_actual = serializers.DecimalField(max_digits=14, decimal_places=2)


class CambiarEstadoPedidoSerializer(serializers.Serializer):
    estado_codigo = serializers.ChoiceField(
        choices=[
            "EN_PRODUCCION",
            "LISTO_ENTREGA",
            "ENTREGADO",
        ]
    )


class PedidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pedido
        fields = "__all__"
        read_only_fields = [field.name for field in Pedido._meta.fields]


class PedidoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Pedido.objects.all()
    serializer_class = PedidoSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        queryset = Pedido.objects.select_related("proforma", "estado").order_by("-id")
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(proforma__vendedor=self.request.user)

    @extend_schema(
        request=CambiarEstadoPedidoSerializer,
        responses={200: PedidoSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="cambiar-estado",
    )
    def cambiar_estado(self, request, pk=None):
        datos = CambiarEstadoPedidoSerializer(
            data=request.data,
        )
        datos.is_valid(raise_exception=True)

        pedido = cambiar_estado_pedido(
            pedido_id=self.get_object().id,
            actor=request.user,
            estado_codigo=datos.validated_data["estado_codigo"],
        )

        return Response(self.get_serializer(pedido).data)

    @extend_schema(
        request=None,
        responses={200: PedidoSerializer},
    )
    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        pedido = cancelar_pedido(
            pedido_id=self.get_object().id,
            actor=request.user,
        )
        return Response(self.get_serializer(pedido).data)

    @extend_schema(request=EmitirReciboSerializer, responses={201: ReciboSerializer})
    @action(detail=True, methods=["post"])
    def emitir_recibo(self, request, pk=None):
        datos = EmitirReciboSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        recibo = emitir_recibo(pedido=self.get_object(), actor=request.user, **datos.validated_data)
        return Response(ReciboSerializer(recibo).data, status=201)

    @extend_schema(request=None, responses={201: NotaEntregaSerializer})
    @action(detail=True, methods=["post"])
    def emitir_nota_entrega(self, request, pk=None):
        nota = emitir_nota(pedido=self.get_object(), actor=request.user)
        return Response(NotaEntregaSerializer(nota).data, status=201)
