from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalogo.models import ValorCatalogo
from apps.core.permissions import EsVendedor
from apps.core.serializers import UsuarioResumenSerializer, resumen_usuario
from apps.notas_entrega.api.views import NotaEntregaSerializer
from apps.notas_entrega.services import emitir_nota
from apps.pedidos.models import Pedido
from apps.pedidos.services import cambiar_estado_pedido, cancelar_pedido
from apps.proformas.api.serializers import ClienteResumenProformaSerializer
from apps.recibos.api.views import ReciboSerializer
from apps.recibos.services import emitir_recibo_idempotente


class EmitirReciboSerializer(serializers.Serializer):
    nombre_completo = serializers.CharField(max_length=250)
    monto_en_letras = serializers.CharField()
    concepto = serializers.CharField()
    tipo_pago = serializers.PrimaryKeyRelatedField(queryset=ValorCatalogo.objects.all())
    numero_cheque = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    banco = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    pago_actual = serializers.DecimalField(max_digits=14, decimal_places=2)
    clave_idempotencia = serializers.UUIDField(required=False, allow_null=True)


class CambiarEstadoPedidoSerializer(serializers.Serializer):
    estado_codigo = serializers.ChoiceField(
        choices=[
            "EN_PRODUCCION",
            "LISTO_ENTREGA",
            "ENTREGADO",
        ]
    )


class PedidoSerializer(serializers.ModelSerializer):
    proforma_numero = serializers.IntegerField(source="proforma.numero", read_only=True)
    proforma_titulo = serializers.CharField(
        source="proforma.titulo", read_only=True, allow_null=True
    )
    cliente_resumen = serializers.SerializerMethodField()
    vendedor_resumen = serializers.SerializerMethodField()

    class Meta:
        model = Pedido
        fields = "__all__"
        read_only_fields = [field.name for field in Pedido._meta.fields]

    @extend_schema_field(ClienteResumenProformaSerializer(allow_null=True))
    def get_cliente_resumen(self, pedido):
        proforma = getattr(pedido, "proforma", None)
        if proforma is None or proforma.cliente_id is None:
            return None
        cliente = proforma.cliente
        nombre_actual = " ".join(
            value.strip()
            for value in [cliente.nombres or "", cliente.apellidos or ""]
            if value.strip()
        )
        tiene_snapshot = any(
            value is not None
            for value in [
                proforma.cliente_nombre_snapshot,
                proforma.cliente_empresa_snapshot,
                proforma.cliente_celular_snapshot,
            ]
        )
        return {
            "id": proforma.cliente_id,
            "nombre": proforma.cliente_nombre_snapshot if tiene_snapshot else nombre_actual,
            "empresa": proforma.cliente_empresa_snapshot if tiene_snapshot else cliente.empresa,
            "celular": proforma.cliente_celular_snapshot if tiene_snapshot else cliente.celular,
        }

    @extend_schema_field(UsuarioResumenSerializer(allow_null=True))
    def get_vendedor_resumen(self, pedido):
        proforma = getattr(pedido, "proforma", None)
        return resumen_usuario(getattr(proforma, "vendedor", None))


class PedidoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Pedido.objects.all()
    serializer_class = PedidoSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        return Pedido.objects.select_related(
            "proforma__cliente", "proforma__vendedor", "estado"
        ).order_by("-id")

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

    @extend_schema(
        request=EmitirReciboSerializer,
        responses={200: ReciboSerializer, 201: ReciboSerializer},
        parameters=[
            OpenApiParameter(
                name="Idempotency-Key",
                location=OpenApiParameter.HEADER,
                required=False,
                type=str,
            )
        ],
    )
    @action(detail=True, methods=["post"])
    def emitir_recibo(self, request, pk=None):
        datos = EmitirReciboSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        payload = dict(datos.validated_data)
        clave = payload.pop("clave_idempotencia", None) or request.headers.get("Idempotency-Key")
        recibo, replay = emitir_recibo_idempotente(
            pedido=self.get_object(),
            actor=request.user,
            clave_idempotencia=clave,
            **payload,
        )
        return Response(
            ReciboSerializer(recibo).data,
            status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED,
        )

    @extend_schema(request=None, responses={201: NotaEntregaSerializer})
    @action(detail=True, methods=["post"])
    def emitir_nota_entrega(self, request, pk=None):
        nota = emitir_nota(pedido=self.get_object(), actor=request.user)
        return Response(NotaEntregaSerializer(nota).data, status=201)
