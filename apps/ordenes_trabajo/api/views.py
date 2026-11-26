from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.permissions import (
    EsOperadorOrdenTrabajo,
    es_encargado_tienda,
    es_jefe_taller,
)
from apps.core.serializers import UsuarioResumenSerializer, resumen_usuario
from apps.documentos.http import respuesta_documento_html, respuesta_documento_pdf
from apps.documentos.pdf import renderizar_orden_trabajo_pdf
from apps.documentos.services import renderizar_orden_trabajo
from apps.ordenes_trabajo.models import HistorialEstadoOrdenTrabajo, OrdenTrabajo
from apps.ordenes_trabajo.services import (
    cambiar_estado_orden_trabajo,
    puede_cambiar_estado_orden_trabajo,
)
from apps.pedidos.services import cambiar_estado_pedido
from apps.proformas.api.serializers import (
    ClienteResumenProformaSerializer,
    EspecificacionMuebleSerializer,
    ValorCatalogoResumenSerializer,
)
from apps.proformas.models import (
    DetalleProforma,
    resolver_fecha_hora_comercial,
    subquery_fecha_hora_procedencia,
)


class DetalleOrdenTrabajoSerializer(serializers.ModelSerializer):
    tipo_item_info = ValorCatalogoResumenSerializer(source="tipo_item", read_only=True)
    unidad_info = ValorCatalogoResumenSerializer(source="unidad", read_only=True)
    especificacion = serializers.SerializerMethodField()
    descripcion = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = DetalleProforma
        fields = [
            "id",
            "tipo_item_info",
            "producto",
            "familia_producto",
            "nombre",
            "descripcion",
            "cantidad",
            "unidad_info",
            "especificacion",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if (
            instance.tipo_item.codigo != "MUEBLE_MEDIDA"
            or request is None
            or not es_jefe_taller(request.user)
        ):
            data["descripcion"] = None
        return data

    @extend_schema_field(EspecificacionMuebleSerializer(allow_null=True))
    def get_especificacion(self, detalle):
        request = self.context.get("request")
        if request is None or not es_jefe_taller(request.user):
            return None
        if detalle.tipo_item.codigo != "MUEBLE_MEDIDA":
            return None
        especificacion = getattr(detalle, "especificacionmueble", None)
        if especificacion is None:
            return None
        return EspecificacionMuebleSerializer(especificacion).data


class HistorialEstadoOrdenTrabajoSerializer(serializers.ModelSerializer):
    estado_anterior_info = ValorCatalogoResumenSerializer(
        source="estado_anterior", read_only=True, allow_null=True
    )
    estado_nuevo_info = ValorCatalogoResumenSerializer(source="estado_nuevo", read_only=True)
    cambiado_por_resumen = serializers.SerializerMethodField()

    class Meta:
        model = HistorialEstadoOrdenTrabajo
        fields = [
            "id",
            "estado_anterior",
            "estado_anterior_info",
            "estado_nuevo",
            "estado_nuevo_info",
            "cambiado_por",
            "cambiado_por_resumen",
            "fecha",
            "observaciones",
        ]
        read_only_fields = fields

    @extend_schema_field(UsuarioResumenSerializer(allow_null=True))
    def get_cambiado_por_resumen(self, item):
        return resumen_usuario(getattr(item, "cambiado_por", None))


class OrdenTrabajoSerializer(serializers.ModelSerializer):
    estado_info = ValorCatalogoResumenSerializer(source="estado", read_only=True)
    estado_saldo_info = ValorCatalogoResumenSerializer(
        source="estado_saldo",
        read_only=True,
        allow_null=True,
    )
    proforma_numero = serializers.IntegerField(
        source="pedido.proforma.numero",
        read_only=True,
    )
    proforma_titulo = serializers.CharField(
        source="pedido.proforma.titulo",
        read_only=True,
        allow_null=True,
    )
    pedido_estado_codigo = serializers.CharField(
        source="pedido.estado.codigo",
        read_only=True,
    )
    pedido_estado_nombre = serializers.CharField(
        source="pedido.estado.nombre",
        read_only=True,
    )
    cliente_resumen = serializers.SerializerMethodField()
    vendedor_resumen = serializers.SerializerMethodField()
    detalles = DetalleOrdenTrabajoSerializer(
        source="pedido.proforma.detalles",
        many=True,
        read_only=True,
    )
    fecha_hora = serializers.SerializerMethodField()
    historial_estados = HistorialEstadoOrdenTrabajoSerializer(many=True, read_only=True)
    puede_cambiar_estado = serializers.SerializerMethodField()

    class Meta:
        model = OrdenTrabajo
        fields = [
            "id",
            "pedido",
            "pedido_estado_codigo",
            "pedido_estado_nombre",
            "proforma_numero",
            "proforma_titulo",
            "cliente_resumen",
            "vendedor_resumen",
            "jefe_taller",
            "numero",
            "fecha",
            "fecha_hora",
            "fecha_inicio",
            "fecha_fin",
            "responsable_recepcion",
            "fecha_entrega",
            "lugar_entrega",
            "estado_saldo",
            "estado_saldo_info",
            "estado",
            "estado_info",
            "created_by",
            "updated_by",
            "puede_cambiar_estado",
            "detalles",
            "historial_estados",
        ]
        read_only_fields = fields

    def get_puede_cambiar_estado(self, orden) -> bool:
        request = self.context.get("request")
        return bool(request and puede_cambiar_estado_orden_trabajo(request.user))

    @extend_schema_field(ClienteResumenProformaSerializer(allow_null=True))
    def get_cliente_resumen(self, orden):
        proforma = orden.pedido.proforma
        if proforma.cliente_id is None:
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
    def get_vendedor_resumen(self, orden):
        proforma = getattr(orden.pedido, "proforma", None)
        return resumen_usuario(getattr(proforma, "vendedor", None))

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_fecha_hora(self, orden):
        return resolver_fecha_hora_comercial(orden, "ORDEN_TRABAJO")


class CambiarEstadoOrdenTrabajoSerializer(serializers.Serializer):
    estado_codigo = serializers.ChoiceField(
        choices=[
            ("EN_PROCESO", "En proceso"),
            ("TERMINADA", "Terminada"),
        ]
    )
    observaciones = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PlanificacionOrdenTrabajoSerializer(serializers.Serializer):
    fecha_inicio = serializers.DateField(required=False, allow_null=True)
    fecha_fin = serializers.DateField(required=False, allow_null=True)
    fecha_entrega = serializers.DateField(required=False, allow_null=True)
    lugar_entrega = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    responsable_recepcion = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=200
    )

    def validate(self, attrs):
        fecha_inicio = attrs.get("fecha_inicio", getattr(self.instance, "fecha_inicio", None))
        fecha_fin = attrs.get("fecha_fin", getattr(self.instance, "fecha_fin", None))
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            raise serializers.ValidationError(
                {"fecha_fin": ("La fecha de fin de fabricación no puede ser anterior al inicio.")}
            )
        return attrs


class OrdenTrabajoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OrdenTrabajo.objects.all()
    serializer_class = OrdenTrabajoSerializer
    permission_classes = [EsOperadorOrdenTrabajo]

    def get_queryset(self):
        queryset = (
            OrdenTrabajo.objects.select_related(
                "pedido__estado",
                "pedido__proforma__cliente",
                "pedido__proforma__vendedor",
                "estado",
                "estado_saldo",
            )
            .prefetch_related(
                "pedido__proforma__detalles__tipo_item",
                "pedido__proforma__detalles__unidad",
                "pedido__proforma__detalles__producto",
                "pedido__proforma__detalles__especificacionmueble__tipo_mueble",
                "historial_estados__estado_anterior",
                "historial_estados__estado_nuevo",
                "historial_estados__cambiado_por",
            )
            .annotate(fecha_hora_procedencia=subquery_fecha_hora_procedencia("ORDEN_TRABAJO"))
            .order_by("-id")
        )
        user = self.request.user
        solo_taller = (
            es_jefe_taller(user)
            and not (user.is_staff or user.is_superuser)
            and not es_encargado_tienda(user)
        )
        if solo_taller:
            queryset = queryset.filter(
                pedido__proforma__detalles__tipo_item__codigo="MUEBLE_MEDIDA"
            ).distinct()
        from apps.core.excel_bandejas import validar_rango_fechas

        estado = (self.request.query_params.get("estado") or "").strip()
        if estado:
            if estado.isdigit():
                queryset = queryset.filter(estado_id=int(estado))
            else:
                queryset = queryset.filter(estado__codigo__iexact=estado)
        fecha_desde, fecha_hasta = validar_rango_fechas(
            self.request.query_params.get("fecha_desde"),
            self.request.query_params.get("fecha_hasta"),
        )
        if fecha_desde:
            queryset = queryset.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            queryset = queryset.filter(fecha__lte=fecha_hasta)
        tipo = (self.request.query_params.get("tipo") or "").strip().upper()
        if tipo == "MUEBLE_MEDIDA":
            queryset = queryset.filter(
                pedido__proforma__detalles__tipo_item__codigo="MUEBLE_MEDIDA"
            ).distinct()
        elif tipo == "CATALOGO":
            queryset = queryset.exclude(
                pedido__proforma__detalles__tipo_item__codigo="MUEBLE_MEDIDA"
            ).distinct()
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            from django.db.models import Q

            q = (
                Q(pedido__proforma__titulo__icontains=search)
                | Q(pedido__proforma__cliente_nombre_snapshot__icontains=search)
                | Q(pedido__proforma__cliente__nombres__icontains=search)
                | Q(pedido__proforma__cliente__apellidos__icontains=search)
                | Q(lugar_entrega__icontains=search)
            )
            if search.isdigit():
                q |= (
                    Q(numero=int(search))
                    | Q(pedido_id=int(search))
                    | Q(pedido__proforma__numero=int(search))
                )
            queryset = queryset.filter(q)
        return queryset

    @extend_schema(
        request=None,
        responses={(200, "text/html"): OpenApiTypes.STR},
    )
    @action(detail=True, methods=["get"])
    def documento(self, request, pk=None):
        orden = self.get_object()
        return respuesta_documento_html(
            contenido=renderizar_orden_trabajo(orden.id, actor=request.user),
            nombre=f"orden-trabajo-{orden.numero}",
        )

    @extend_schema(request=None, responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(
        detail=True,
        methods=["get"],
        url_path="documento-pdf",
        pagination_class=None,
        filter_backends=[],
    )
    def documento_pdf(self, request, pk=None):
        orden = self.get_object()
        return respuesta_documento_pdf(
            contenido=renderizar_orden_trabajo_pdf(orden.id, usuario=request.user),
            nombre=f"orden-trabajo-{orden.numero}",
        )

    @extend_schema(
        request=CambiarEstadoOrdenTrabajoSerializer,
        responses={200: OrdenTrabajoSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="cambiar-estado",
    )
    def cambiar_estado(self, request, pk=None):
        orden = self.get_object()
        serializer = CambiarEstadoOrdenTrabajoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        orden = cambiar_estado_orden_trabajo(
            orden_trabajo_id=orden.id,
            actor=request.user,
            estado_codigo=serializer.validated_data["estado_codigo"],
            observaciones=serializer.validated_data.get("observaciones"),
        )
        return Response(self.get_serializer(orden).data)

    @extend_schema(request=None, responses={200: OrdenTrabajoSerializer})
    @action(
        detail=True,
        methods=["post"],
        url_path="marcar-listo-entrega",
    )
    def marcar_listo_entrega(self, request, pk=None):
        if not puede_cambiar_estado_orden_trabajo(request.user):
            raise PermissionDenied(
                "Solo el rol JEFE_TALLER puede marcar una orden de trabajo como lista para entrega."
            )
        orden = self.get_object()
        tiene_muebles = orden.pedido.proforma.detalles.filter(
            tipo_item__codigo="MUEBLE_MEDIDA"
        ).exists()
        if tiene_muebles and orden.estado.codigo != "TERMINADA":
            raise serializers.ValidationError(
                {
                    "estado": (
                        "La orden de trabajo debe estar TERMINADA antes de marcar el pedido "
                        "como listo para entrega."
                    )
                }
            )
        cambiar_estado_pedido(
            pedido_id=orden.pedido_id,
            actor=request.user,
            estado_codigo="LISTO_ENTREGA",
        )
        orden.refresh_from_db()
        return Response(self.get_serializer(orden).data)

    @extend_schema(
        request=PlanificacionOrdenTrabajoSerializer,
        responses={200: OrdenTrabajoSerializer},
    )
    @action(
        detail=True,
        methods=["patch"],
        url_path="planificacion",
    )
    def planificacion(self, request, pk=None):
        orden = self.get_object()
        serializer = PlanificacionOrdenTrabajoSerializer(
            instance=orden,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        update_fields = ["updated_by"]
        for field, value in serializer.validated_data.items():
            if isinstance(value, str):
                value = value.strip() or None
            setattr(orden, field, value)
            update_fields.append(field)
        orden.updated_by = request.user
        orden.save(update_fields=update_fields)
        return Response(self.get_serializer(orden).data)

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
        from apps.core.excel_bandejas import exportar_ordenes_trabajo_excel

        return exportar_ordenes_trabajo_excel(
            self.filter_queryset(self.get_queryset()), request.query_params
        )
