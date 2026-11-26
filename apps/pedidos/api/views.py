from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalogo.models import ValorCatalogo
from apps.core.permissions import EsVendedor
from apps.core.serializers import UsuarioResumenSerializer, resumen_usuario
from apps.notas_entrega.api.views import NotaEntregaSerializer
from apps.notas_entrega.services import emitir_nota
from apps.pedidos.models import HistorialEstadoPedido, Pedido
from apps.pedidos.services import cambiar_estado_pedido, cancelar_pedido
from apps.proformas.api.serializers import (
    ClienteResumenProformaSerializer,
    ValorCatalogoResumenSerializer,
)
from apps.proformas.models import RegistroProcedenciaImportacion
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


class HistorialEstadoPedidoSerializer(serializers.ModelSerializer):
    estado_anterior_info = ValorCatalogoResumenSerializer(
        source="estado_anterior", read_only=True, allow_null=True
    )
    estado_nuevo_info = ValorCatalogoResumenSerializer(source="estado_nuevo", read_only=True)
    cambiado_por_resumen = serializers.SerializerMethodField()

    class Meta:
        model = HistorialEstadoPedido
        fields = [
            "id",
            "estado_anterior",
            "estado_anterior_info",
            "estado_nuevo",
            "estado_nuevo_info",
            "cambiado_por",
            "cambiado_por_resumen",
            "es_automatico",
            "origen",
            "fecha",
            "observaciones",
        ]
        read_only_fields = fields

    @extend_schema_field(UsuarioResumenSerializer(allow_null=True))
    def get_cambiado_por_resumen(self, item):
        return resumen_usuario(getattr(item, "cambiado_por", None))


class PedidoSerializer(serializers.ModelSerializer):
    proforma_numero = serializers.IntegerField(source="proforma.numero", read_only=True)
    proforma_titulo = serializers.CharField(
        source="proforma.titulo", read_only=True, allow_null=True
    )
    cliente_resumen = serializers.SerializerMethodField()
    vendedor_resumen = serializers.SerializerMethodField()
    fecha_entrega_programada = serializers.SerializerMethodField()
    nota_entrega_fecha = serializers.SerializerMethodField()
    naturaleza = serializers.SerializerMethodField()
    historial_estados = HistorialEstadoPedidoSerializer(many=True, read_only=True)
    historial_incompleto = serializers.SerializerMethodField()

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

    @extend_schema_field(serializers.DateField(allow_null=True))
    def get_fecha_entrega_programada(self, pedido):
        ot = getattr(pedido, "ordentrabajo", None)
        return getattr(ot, "fecha_entrega", None)

    @extend_schema_field(serializers.DateField(allow_null=True))
    def get_nota_entrega_fecha(self, pedido):
        nota = getattr(pedido, "notaentrega", None)
        return getattr(nota, "fecha", None)

    def get_naturaleza(self, pedido) -> str:
        proc = RegistroProcedenciaImportacion.objects.filter(
            entidad="PEDIDO", objeto_id=pedido.pk
        ).first()
        return proc.naturaleza if proc else "REAL"

    @extend_schema_field(serializers.BooleanField())
    def get_historial_incompleto(self, pedido):
        eventos = list(pedido.historial_estados.all())
        if not eventos:
            return True
        if any(e.origen == "RECUPERACION" for e in eventos):
            return True
        primero = min(eventos, key=lambda e: (e.fecha, e.id))
        return primero.estado_anterior_id is not None or primero.estado_nuevo.codigo != "CONFIRMADO"


class PedidoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Pedido.objects.all()
    serializer_class = PedidoSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        queryset = Pedido.objects.select_related(
            "proforma__cliente",
            "proforma__vendedor",
            "estado",
            "ordentrabajo",
            "notaentrega",
        ).prefetch_related(
            "historial_estados__estado_anterior",
            "historial_estados__estado_nuevo",
            "historial_estados__cambiado_por",
        )
        estado = self.request.query_params.get("estado")
        if estado:
            queryset = queryset.filter(estado__codigo__iexact=estado.strip())
        fecha_desde = self.request.query_params.get("fecha_desde")
        if fecha_desde:
            queryset = queryset.filter(fecha_confirmacion__date__gte=fecha_desde)
        fecha_hasta = self.request.query_params.get("fecha_hasta")
        if fecha_hasta:
            queryset = queryset.filter(fecha_confirmacion__date__lte=fecha_hasta)
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            from django.db.models import Q

            q = (
                Q(proforma__titulo__icontains=search)
                | Q(proforma__cliente_nombre_snapshot__icontains=search)
                | Q(proforma__cliente_empresa_snapshot__icontains=search)
                | Q(proforma__cliente__nombres__icontains=search)
                | Q(proforma__cliente__apellidos__icontains=search)
                | Q(proforma__cliente__empresa__icontains=search)
            )
            if search.isdigit():
                q |= Q(id=int(search)) | Q(proforma__numero=int(search))
            queryset = queryset.filter(q)
        ordering = self.request.query_params.get("ordering")
        permitidos = {
            "id",
            "-id",
            "fecha_confirmacion",
            "-fecha_confirmacion",
            "fecha_entrega_efectiva",
            "-fecha_entrega_efectiva",
        }
        if ordering in permitidos:
            return queryset.order_by(ordering, "-id")
        return queryset.order_by("-fecha_confirmacion", "-id")

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

    @extend_schema(
        request=None,
        responses={
            (
                200,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ): OpenApiTypes.BINARY
        },
    )
    @action(detail=False, methods=["get"], url_path="exportar-excel", pagination_class=None)
    def exportar_excel(self, request):
        from apps.core.excel_bandejas import exportar_pedidos_excel

        return exportar_pedidos_excel(
            self.filter_queryset(self.get_queryset()), request.query_params
        )
