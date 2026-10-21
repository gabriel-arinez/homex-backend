from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogo.models import ValorCatalogo
from apps.clientes.api.fields import ClienteVisibleField
from apps.clientes.models import Cliente
from apps.clientes.validacion import tipos_cliente_activos, validar_identidad_cliente
from apps.proformas.models import DetalleProforma, EspecificacionMueble, Proforma
from apps.proformas.revision import revision_proforma
from apps.proformas.validacion_tecnica import validar_datos_tecnicos


class ValorCatalogoResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValorCatalogo
        fields = ["id", "codigo", "nombre"]
        read_only_fields = fields


class ClienteResumenProformaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.CharField(allow_null=True, allow_blank=True)
    empresa = serializers.CharField(allow_null=True, allow_blank=True)
    celular = serializers.CharField(allow_null=True, allow_blank=True)


class ProformaFiltrosListadoSerializer(serializers.Serializer):
    search = serializers.CharField(
        required=False,
        allow_blank=False,
        help_text="Número de proforma, título o datos del cliente.",
    )
    estado = serializers.CharField(required=False, max_length=80)
    moneda = serializers.CharField(required=False, max_length=80)
    cliente = serializers.IntegerField(required=False, min_value=1)
    fecha_desde = serializers.DateField(required=False)
    fecha_hasta = serializers.DateField(required=False)

    def validate(self, attrs):
        desde = attrs.get("fecha_desde")
        hasta = attrs.get("fecha_hasta")
        if desde and hasta and desde > hasta:
            raise serializers.ValidationError(
                {"fecha_hasta": "Debe ser igual o posterior a fecha_desde."}
            )
        return attrs


class EspecificacionMuebleSerializer(serializers.ModelSerializer):
    tipo_mueble_info = ValorCatalogoResumenSerializer(
        source="tipo_mueble",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = EspecificacionMueble
        fields = [
            "id",
            "proforma_detalle",
            "tipo_mueble",
            "tipo_mueble_info",
            "datos_tecnicos",
            "observaciones",
        ]
        read_only_fields = ["id", "proforma_detalle", "tipo_mueble_info"]

    def validate_datos_tecnicos(self, datos):
        anteriores = self.instance.datos_tecnicos if self.instance else None
        return validar_datos_tecnicos(datos, anteriores=anteriores)

    def validate_tipo_mueble(self, valor):
        if valor is None:
            return valor
        if valor.concepto.codigo != "TIPO_MUEBLE":
            raise serializers.ValidationError("Seleccione un tipo de mueble válido.")
        if not valor.activo and (self.instance is None or self.instance.tipo_mueble_id != valor.pk):
            raise serializers.ValidationError("El tipo de mueble seleccionado no está activo.")
        return valor


class DetalleProformaSerializer(serializers.ModelSerializer):
    especificacion = EspecificacionMuebleSerializer(source="especificacionmueble", read_only=True)
    tipo_item_info = ValorCatalogoResumenSerializer(source="tipo_item", read_only=True)
    unidad_info = ValorCatalogoResumenSerializer(source="unidad", read_only=True)

    class Meta:
        model = DetalleProforma
        fields = [
            "id",
            "proforma",
            "tipo_item",
            "tipo_item_info",
            "producto",
            "familia_producto",
            "nombre",
            "descripcion",
            "cantidad",
            "unidad",
            "unidad_info",
            "modo_calculo",
            "precio_unitario",
            "importe_negociado",
            "descuento",
            "precio_antes_snapshot",
            "precio_ahora_snapshot",
            "total",
            "especificacion",
        ]
        read_only_fields = [
            "proforma",
            "tipo_item_info",
            "unidad_info",
            "total",
            "precio_antes_snapshot",
            "precio_ahora_snapshot",
        ]
        extra_kwargs = {
            "precio_unitario": {
                "help_text": (
                    "Para líneas nuevas PRECIO_UNITARIO, el precio es obligatorio y "
                    "mayor que cero. En una edición puede omitirse para conservar el "
                    "valor persistido. Las líneas históricas TOTAL_NEGOCIADO preservan "
                    "su importe y no están sujetas a esa validación."
                )
            }
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        modo = attrs.get(
            "modo_calculo",
            getattr(self.instance, "modo_calculo", "PRECIO_UNITARIO"),
        )
        precio = attrs.get(
            "precio_unitario",
            getattr(self.instance, "precio_unitario", None),
        )
        if modo == "PRECIO_UNITARIO" and (precio is None or precio <= 0):
            raise serializers.ValidationError(
                {"precio_unitario": "Debe registrar un precio unitario mayor que cero."}
            )
        self._validar_variante_catalogo(attrs)
        return attrs

    def _validar_variante_catalogo(self, attrs):
        instancia = self.instance
        tipo = attrs.get("tipo_item", getattr(instancia, "tipo_item", None))
        producto = attrs.get("producto", getattr(instancia, "producto", None))
        familia = attrs.get("familia_producto", getattr(instancia, "familia_producto", None))
        unidad = attrs.get("unidad", getattr(instancia, "unidad", None))
        if tipo is None or unidad is None:
            return

        if tipo.codigo == "MUEBLE_MEDIDA":
            if producto is not None or familia is not None:
                raise serializers.ValidationError(
                    {"producto": "Un mueble a medida no apunta al catálogo."}
                )
            return
        if producto is None:
            if familia is None:
                raise serializers.ValidationError(
                    {"familia_producto": "Seleccione una familia para la variante pendiente."}
                )
            familia_cambio = instancia is None or familia.pk != instancia.familia_producto_id
            if familia_cambio and not familia.activo:
                raise serializers.ValidationError(
                    {"familia_producto": "La familia pendiente debe estar activa."}
                )
            return

        producto_cambio = instancia is None or producto.pk != instancia.producto_id
        if producto_cambio and not producto.activo:
            raise serializers.ValidationError({"producto": "La variante debe estar activa."})
        if familia is not None and producto.familia_id != familia.pk:
            raise serializers.ValidationError(
                {"producto": "La variante no pertenece a la familia seleccionada."}
            )
        if producto.categoria.codigo != tipo.codigo:
            raise serializers.ValidationError(
                {"producto": "La variante no corresponde al tipo de ítem."}
            )
        if producto.unidad_stock_id != unidad.pk:
            raise serializers.ValidationError(
                {"unidad": "La unidad no coincide con la unidad de stock de la variante."}
            )


class ProformaSerializer(serializers.ModelSerializer):
    cliente = ClienteVisibleField(required=False, allow_null=True)
    detalles = DetalleProformaSerializer(many=True, read_only=True)
    estado_info = ValorCatalogoResumenSerializer(source="estado", read_only=True)
    moneda_info = ValorCatalogoResumenSerializer(source="moneda", read_only=True)
    cliente_resumen = serializers.SerializerMethodField()
    revision = serializers.SerializerMethodField()

    class Meta:
        model = Proforma
        fields = [
            "id",
            "numero",
            "revision",
            "cliente",
            "cliente_resumen",
            "vendedor",
            "estado",
            "estado_info",
            "titulo",
            "fecha",
            "plazo_entrega",
            "validez_oferta",
            "porcentaje_adelanto",
            "moneda",
            "moneda_info",
            "subtotal",
            "descuento_total",
            "total",
            "observaciones",
            "prospecto_nombre",
            "prospecto_empresa",
            "prospecto_celular",
            "prospecto_direccion",
            "cliente_nombre_snapshot",
            "cliente_empresa_snapshot",
            "cliente_celular_snapshot",
            "cliente_direccion_snapshot",
            "created_by",
            "updated_by",
            "detalles",
        ]
        read_only_fields = [
            "numero",
            "revision",
            "cliente_resumen",
            "vendedor",
            "estado",
            "estado_info",
            "fecha",
            "moneda_info",
            "subtotal",
            "descuento_total",
            "total",
            "cliente_nombre_snapshot",
            "cliente_empresa_snapshot",
            "cliente_celular_snapshot",
            "cliente_direccion_snapshot",
            "created_by",
            "updated_by",
        ]

    @extend_schema_field(serializers.CharField())
    def get_revision(self, proforma):
        return revision_proforma(proforma)

    @extend_schema_field(ClienteResumenProformaSerializer(allow_null=True))
    def get_cliente_resumen(self, proforma):
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


class ProformaListadoSerializer(ProformaSerializer):
    class Meta(ProformaSerializer.Meta):
        fields = [
            "id",
            "numero",
            "cliente",
            "cliente_resumen",
            "vendedor",
            "estado",
            "estado_info",
            "titulo",
            "fecha",
            "plazo_entrega",
            "validez_oferta",
            "porcentaje_adelanto",
            "moneda",
            "moneda_info",
            "subtotal",
            "descuento_total",
            "total",
        ]


class CrearProformaSerializer(serializers.ModelSerializer):
    cliente = ClienteVisibleField(required=False, allow_null=True)
    moneda_codigo = serializers.ChoiceField(choices=["BOB", "USD"], default="BOB", write_only=True)

    class Meta:
        model = Proforma
        fields = [
            "cliente",
            "titulo",
            "plazo_entrega",
            "validez_oferta",
            "porcentaje_adelanto",
            "moneda_codigo",
            "observaciones",
            "prospecto_nombre",
            "prospecto_empresa",
            "prospecto_celular",
            "prospecto_direccion",
        ]


class ClienteNuevoProformaSerializer(serializers.ModelSerializer):
    tipo_cliente = serializers.PrimaryKeyRelatedField(queryset=tipos_cliente_activos())

    class Meta:
        model = Cliente
        fields = [
            "tipo_cliente",
            "nombres",
            "apellidos",
            "empresa",
            "celular",
            "direccion",
            "observaciones",
        ]

    def validate(self, attrs):
        return validar_identidad_cliente(attrs)


class DetalleIntegralSerializer(DetalleProformaSerializer):
    captura_asistida_id = serializers.IntegerField(required=False, min_value=1, write_only=True)
    id = serializers.IntegerField(required=False)
    especificacion = EspecificacionMuebleSerializer(required=False, allow_null=True)

    def to_internal_value(self, data):
        # La validación del JSON anidado ocurre ANTES de validate(). Conectar
        # la ficha existente evita rechazar un legado idéntico de >40 piezas
        # al guardar cambios comerciales mediante PUT integral.
        campo = self.fields["especificacion"]
        previa = campo.instance
        campo.instance = None
        proforma = self.context.get("proforma_actual")
        if proforma is not None and isinstance(data, dict) and data.get("id"):
            detalle = next(
                (item for item in proforma.detalles.all() if item.id == data["id"]),
                None,
            )
            if detalle is not None:
                campo.instance = getattr(detalle, "especificacionmueble", None)
        try:
            return super().to_internal_value(data)
        finally:
            campo.instance = previa

    class Meta(DetalleProformaSerializer.Meta):
        fields = [*DetalleProformaSerializer.Meta.fields, "captura_asistida_id"]
        read_only_fields = [
            "proforma",
            "tipo_item_info",
            "unidad_info",
            "total",
            "precio_antes_snapshot",
            "precio_ahora_snapshot",
        ]

    def validate(self, attrs):
        # El ListSerializer reutiliza su child: nunca conservar la instancia
        # de la línea anterior en una edición integral.
        proforma = self.context.get("proforma_actual")
        existente = None
        if proforma is not None and attrs.get("id") is not None:
            existente = next(
                (linea for linea in proforma.detalles.all() if linea.id == attrs["id"]),
                None,
            )
        instancia_anterior = self.instance
        self.instance = existente
        try:
            attrs = super().validate(attrs)
        finally:
            self.instance = instancia_anterior

        modo = attrs.get(
            "modo_calculo",
            existente.modo_calculo if existente else "PRECIO_UNITARIO",
        )
        if modo != "PRECIO_UNITARIO":
            if not (existente and modo == "TOTAL_NEGOCIADO"):
                raise serializers.ValidationError(
                    {"modo_calculo": "Los ítems nuevos sólo admiten PRECIO_UNITARIO."}
                )
        cantidad = attrs.get("cantidad", existente.cantidad if existente else None)
        precio = attrs.get("precio_unitario", existente.precio_unitario if existente else None)
        descuento = attrs.get("descuento", existente.descuento if existente else None)
        if (
            modo == "PRECIO_UNITARIO"
            and cantidad is not None
            and precio is not None
            and descuento is not None
            and descuento > cantidad * precio
        ):
            raise serializers.ValidationError(
                {"descuento": "No puede superar el importe bruto de la línea."}
            )
        if attrs.get("captura_asistida_id") and (
            attrs.get("id")
            or attrs.get("producto")
            or attrs.get("tipo_item").codigo != "MUEBLE_MEDIDA"
        ):
            raise serializers.ValidationError({"captura_asistida_id": "Sólo para muebles nuevos."})
        return attrs


class ProformaIntegralSerializer(serializers.Serializer):
    sesion_borrador = serializers.UUIDField(required=False, write_only=True)
    clave_idempotencia = serializers.UUIDField()
    revision_esperada = serializers.CharField(required=False, min_length=64, max_length=64)
    emitir = serializers.BooleanField(default=False)
    cliente = ClienteVisibleField(required=False, allow_null=True)
    cliente_nuevo = ClienteNuevoProformaSerializer(required=False, allow_null=True)
    titulo = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=250
    )
    plazo_entrega = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=100
    )
    validez_oferta = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    porcentaje_adelanto = serializers.DecimalField(
        required=False, allow_null=True, max_digits=5, decimal_places=2, min_value=0, max_value=100
    )
    moneda_codigo = serializers.ChoiceField(choices=["BOB", "USD"])
    observaciones = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    prospecto_nombre = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    prospecto_empresa = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    prospecto_celular = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    prospecto_direccion = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    detalles = DetalleIntegralSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        if self.context.get("actualizacion") and not attrs.get("revision_esperada"):
            raise serializers.ValidationError(
                {"revision_esperada": "Debes recargar la proforma antes de modificarla."}
            )
        if attrs.get("cliente") and attrs.get("cliente_nuevo"):
            raise serializers.ValidationError(
                {"cliente_nuevo": "Seleccione un cliente existente o registre uno nuevo, no ambos."}
            )
        detalles = attrs.get("detalles", [])
        productos = [detalle["producto"].id for detalle in detalles if detalle.get("producto")]
        if len(productos) != len(set(productos)):
            raise serializers.ValidationError(
                {"detalles": "Una variante de catálogo no puede repetirse en la proforma."}
            )
        if attrs.get("emitir"):
            if not (attrs.get("cliente") or attrs.get("cliente_nuevo")):
                raise serializers.ValidationError(
                    {"cliente": "Debe seleccionar o registrar un cliente antes de emitir."}
                )
            if not detalles:
                raise serializers.ValidationError(
                    {"detalles": "Debe agregar al menos una línea antes de emitir."}
                )
        return attrs


class AprobarProformaRespuestaSerializer(serializers.Serializer):
    pedido_id = serializers.IntegerField(read_only=True)
    estado = serializers.CharField(read_only=True)


class CargaArchivoImagenSerializer(serializers.Serializer):
    archivo = serializers.ImageField()


class ArchivoAdjuntoSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    nombre = serializers.CharField(read_only=True)
    mime_type = serializers.CharField(read_only=True)
    tamano_bytes = serializers.IntegerField(read_only=True)
    url = serializers.URLField(read_only=True)
