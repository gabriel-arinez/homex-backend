from decimal import Decimal

from django.db import transaction
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.catalogo.models import (
    DescuentoProducto,
    FamiliaProducto,
    MetadatoAtributoMueble,
    Producto,
    ProductoPiso,
    ProductoSilla,
    ValorCatalogo,
)
from apps.catalogo.revision import revision_producto
from apps.catalogo.services import (
    demanda_pendiente_por_producto,
    descuento_vigente,
    estado_stock_producto,
    imagen_principal_publica,
    precio_catalogo_vigente,
    validar_cantidad_segun_unidad,
)
from apps.core.exceptions import ConflictoComercial
from apps.core.permissions import es_administrador_comercial
from apps.core.serializers import UsuarioResumenSerializer


class ValorCatalogoPublicoSerializer(serializers.ModelSerializer):
    concepto_codigo = serializers.CharField(source="concepto.codigo", read_only=True)

    class Meta:
        model = ValorCatalogo
        fields = ["id", "concepto_codigo", "codigo", "nombre"]
        read_only_fields = fields


class FamiliaProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = FamiliaProducto
        fields = ["id", "codigo", "nombre", "descripcion", "activo"]
        read_only_fields = ["id"]


class FamiliaProductoResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = FamiliaProducto
        fields = ["id", "codigo", "nombre"]
        read_only_fields = fields


class ProductoSillaSerializer(serializers.ModelSerializer):
    marca_nombre = serializers.SerializerMethodField()
    color_primario_nombre = serializers.SerializerMethodField()
    color_secundario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = ProductoSilla
        exclude = ["created_by", "updated_by"]
        read_only_fields = [
            "producto",
            "marca_nombre",
            "color_primario_nombre",
            "color_secundario_nombre",
        ]

    def get_marca_nombre(self, obj) -> str | None:
        return obj.marca.nombre if obj.marca_id and obj.marca else None

    def get_color_primario_nombre(self, obj) -> str | None:
        return obj.color_primario.nombre if obj.color_primario_id and obj.color_primario else None

    def get_color_secundario_nombre(self, obj) -> str | None:
        return (
            obj.color_secundario.nombre
            if obj.color_secundario_id and obj.color_secundario
            else None
        )


class ProductoPisoSerializer(serializers.ModelSerializer):
    marca_nombre = serializers.SerializerMethodField()
    tipo_nombre = serializers.SerializerMethodField()
    material_nombre = serializers.SerializerMethodField()
    diseno_nombre = serializers.SerializerMethodField()
    acabado_nombre = serializers.SerializerMethodField()

    class Meta:
        model = ProductoPiso
        exclude = ["created_by", "updated_by"]
        read_only_fields = [
            "producto",
            "marca_nombre",
            "tipo_nombre",
            "material_nombre",
            "diseno_nombre",
            "acabado_nombre",
        ]

    def get_marca_nombre(self, obj) -> str | None:
        return obj.marca.nombre if obj.marca_id and obj.marca else None

    def get_tipo_nombre(self, obj) -> str | None:
        return obj.tipo.nombre if obj.tipo_id and obj.tipo else None

    def get_material_nombre(self, obj) -> str | None:
        return obj.material.nombre if obj.material_id and obj.material else None

    def get_diseno_nombre(self, obj) -> str | None:
        return obj.diseno.nombre if obj.diseno_id and obj.diseno else None

    def get_acabado_nombre(self, obj) -> str | None:
        return obj.acabado.nombre if obj.acabado_id and obj.acabado else None


class DescuentoProductoSerializer(serializers.ModelSerializer):
    vigente = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DescuentoProducto
        exclude = ["created_by", "updated_by"]
        read_only_fields = ["producto", "vigente"]

    def get_vigente(self, descuento) -> bool:
        return descuento_vigente(descuento.producto) is not None


class ImagenPrincipalSerializer(serializers.Serializer):
    original = serializers.URLField()
    ancho = serializers.IntegerField(allow_null=True)
    alto = serializers.IntegerField(allow_null=True)
    variantes = serializers.DictField(child=serializers.URLField())


class CargaImagenSerializer(serializers.Serializer):
    archivo = serializers.ImageField()


class ProductoFiltrosListadoSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=False, max_length=200)
    activo = serializers.BooleanField(required=False)
    categoria = serializers.PrimaryKeyRelatedField(
        queryset=ValorCatalogo.objects.select_related("concepto").all(), required=False
    )
    familia = serializers.PrimaryKeyRelatedField(
        queryset=FamiliaProducto.objects.all(), required=False
    )
    marca = serializers.PrimaryKeyRelatedField(
        queryset=ValorCatalogo.objects.select_related("concepto").all(), required=False
    )
    modelo = serializers.CharField(required=False, allow_blank=False, max_length=150)
    color_primario = serializers.PrimaryKeyRelatedField(
        queryset=ValorCatalogo.objects.select_related("concepto").all(), required=False
    )
    tipo = serializers.PrimaryKeyRelatedField(
        queryset=ValorCatalogo.objects.select_related("concepto").all(), required=False
    )
    material = serializers.PrimaryKeyRelatedField(
        queryset=ValorCatalogo.objects.select_related("concepto").all(), required=False
    )
    diseno = serializers.PrimaryKeyRelatedField(
        queryset=ValorCatalogo.objects.select_related("concepto").all(), required=False
    )
    acabado = serializers.PrimaryKeyRelatedField(
        queryset=ValorCatalogo.objects.select_related("concepto").all(), required=False
    )
    espesor_mm = serializers.DecimalField(
        required=False, max_digits=8, decimal_places=2, min_value=Decimal("0.01")
    )
    unidad_stock = serializers.PrimaryKeyRelatedField(
        queryset=ValorCatalogo.objects.select_related("concepto").all(), required=False
    )
    estado_stock = serializers.ChoiceField(
        choices=["SIN_EXISTENCIAS", "STOCK_BAJO", "NORMAL", "SIN_MINIMO"],
        required=False,
    )

    def validate(self, attrs):
        relaciones = {
            "categoria": "CATEGORIA_PRODUCTO",
            "marca": "MARCA",
            "color_primario": "COLOR",
            "tipo": "TIPO_PISO",
            "material": "MATERIAL_PISO",
            "diseno": "DISENO_PISO",
            "acabado": "ACABADO_PISO",
            "unidad_stock": "UNIDAD_MEDIDA",
        }
        for campo, concepto in relaciones.items():
            valor = attrs.get(campo)
            if valor is not None and valor.concepto.codigo != concepto:
                raise serializers.ValidationError(
                    {campo: f"Debe identificar un valor de {concepto}."}
                )
        especificos = {
            "marca",
            "modelo",
            "color_primario",
            "tipo",
            "material",
            "diseno",
            "acabado",
            "espesor_mm",
            "unidad_stock",
        }
        usados = especificos.intersection(attrs)
        categoria = attrs.get("categoria")
        if usados and categoria is None:
            raise serializers.ValidationError(
                {"categoria": "Es obligatoria al utilizar filtros específicos de producto."}
            )
        codigo = categoria.codigo if categoria else None
        permitidos = {
            "SILLA": {"marca", "modelo", "color_primario"},
            "PISO_FLOTANTE": {"marca", "tipo", "material", "diseno", "acabado", "espesor_mm"},
            "OTRO": {"unidad_stock"},
        }
        incompatibles = usados - permitidos.get(codigo, set())
        if incompatibles:
            raise serializers.ValidationError(
                {
                    campo: f"No es compatible con la categoría {codigo or 'indicada'}."
                    for campo in sorted(incompatibles)
                }
            )
        return attrs


def _validar_valor(valor, concepto: str, campo: str, anterior=None):
    if valor is not None and (
        valor.concepto.codigo != concepto
        or (not valor.activo and (anterior is None or valor.pk != anterior.pk))
    ):
        raise serializers.ValidationError({campo: f"Debe pertenecer a {concepto} y estar activo."})


class ProductoSerializer(serializers.ModelSerializer):
    revision = serializers.SerializerMethodField()
    demanda_pendiente = serializers.SerializerMethodField()
    disponibilidad_referencial = serializers.SerializerMethodField()
    estado_stock = serializers.SerializerMethodField()
    precio_vigente = serializers.SerializerMethodField()
    imagen_principal = serializers.SerializerMethodField()
    categoria_info = ValorCatalogoPublicoSerializer(source="categoria", read_only=True)
    unidad_stock_info = ValorCatalogoPublicoSerializer(source="unidad_stock", read_only=True)
    familia_info = FamiliaProductoResumenSerializer(source="familia", read_only=True)
    silla = ProductoSillaSerializer(source="productosilla", required=False, allow_null=True)
    piso = ProductoPisoSerializer(source="productopiso", required=False, allow_null=True)
    promocion = DescuentoProductoSerializer(
        source="descuentoproducto", required=False, allow_null=True
    )
    creado_por_resumen = UsuarioResumenSerializer(
        source="created_by", read_only=True, allow_null=True
    )

    class Meta:
        model = Producto
        fields = [
            "id",
            "revision",
            "categoria",
            "categoria_info",
            "familia",
            "familia_info",
            "sku",
            "nombre",
            "precio_lista",
            "precio_vigente",
            "stock",
            "stock_minimo",
            "estado_stock",
            "demanda_pendiente",
            "disponibilidad_referencial",
            "unidad_stock",
            "unidad_stock_info",
            "activo",
            "observaciones",
            "revision_humana_voz",
            "imagen_principal",
            "silla",
            "piso",
            "promocion",
            "created_by",
            "creado_por_resumen",
            "updated_by",
        ]
        read_only_fields = ["stock", "created_by", "creado_por_resumen", "updated_by"]
        extra_kwargs = {"sku": {"required": True, "allow_null": False, "allow_blank": False}}

    def validate(self, attrs):
        instance = self.instance
        categoria = attrs.get("categoria", getattr(instance, "categoria", None))
        unidad = attrs.get("unidad_stock", getattr(instance, "unidad_stock", None))
        familia = attrs.get("familia", getattr(instance, "familia", None))
        _validar_valor(
            categoria,
            "CATEGORIA_PRODUCTO",
            "categoria",
            getattr(instance, "categoria", None),
        )
        _validar_valor(
            unidad,
            "UNIDAD_MEDIDA",
            "unidad_stock",
            getattr(instance, "unidad_stock", None),
        )
        if (
            familia is not None
            and not familia.activo
            and (instance is None or familia.pk != instance.familia_id)
        ):
            raise serializers.ValidationError({"familia": "La familia debe estar activa."})
        if instance and "categoria" in attrs and attrs["categoria"] != instance.categoria:
            raise serializers.ValidationError({"categoria": "La categoría es inmutable."})
        if instance and "unidad_stock" in attrs and attrs["unidad_stock"] != instance.unidad_stock:
            raise serializers.ValidationError({"unidad_stock": "La unidad es inmutable."})
        categoria_codigo = categoria.codigo if categoria else None
        unidad_codigo = unidad.codigo if unidad else None
        silla_presente = "productosilla" in attrs and attrs["productosilla"] is not None
        piso_presente = "productopiso" in attrs and attrs["productopiso"] is not None
        if categoria_codigo == "SILLA":
            if not instance and not silla_presente:
                raise serializers.ValidationError({"silla": "La ficha de silla es obligatoria."})
            if unidad_codigo != "PIEZA":
                raise serializers.ValidationError({"unidad_stock": "Una silla se vende por PIEZA."})
            if piso_presente:
                raise serializers.ValidationError({"piso": "Una silla no admite ficha de piso."})
        elif categoria_codigo == "PISO_FLOTANTE":
            if not instance and not piso_presente:
                raise serializers.ValidationError({"piso": "La ficha de piso es obligatoria."})
            if unidad_codigo != "M2":
                raise serializers.ValidationError(
                    {"unidad_stock": "Un piso nuevo se vende por M2."}
                )
            if silla_presente:
                raise serializers.ValidationError({"silla": "Un piso no admite ficha de silla."})
        elif categoria_codigo == "OTRO":
            if unidad_codigo not in {"PIEZA", "JUEGO", "BARRA"}:
                raise serializers.ValidationError(
                    {"unidad_stock": "OTRO admite PIEZA, JUEGO o BARRA."}
                )
            if silla_presente or piso_presente:
                raise serializers.ValidationError({"categoria": "OTRO no admite ficha específica."})
        precio = attrs.get("precio_lista", getattr(instance, "precio_lista", 0))
        if precio < 0:
            raise serializers.ValidationError({"precio_lista": "El precio no puede ser negativo."})
        if "stock_minimo" in attrs:
            request = self.context.get("request")
            usuario = getattr(request, "user", None)
            valor_actual = getattr(instance, "stock_minimo", None) if instance else None
            if attrs["stock_minimo"] != valor_actual and not es_administrador_comercial(usuario):
                raise PermissionDenied(
                    "Solo la administración comercial puede configurar el stock mínimo."
                )
            if attrs["stock_minimo"] is not None:
                try:
                    validar_cantidad_segun_unidad(
                        attrs["stock_minimo"],
                        unidad_codigo or "",
                        permitir_cero=True,
                    )
                except serializers.ValidationError as exc:
                    raise serializers.ValidationError({"stock_minimo": exc.detail}) from exc
        self._validar_fichas(attrs, instance)
        promocion = attrs.get("descuentoproducto")
        if promocion:
            descuento_actual = getattr(instance, "descuentoproducto", None) if instance else None
            antes = promocion.get("precio_antes", getattr(descuento_actual, "precio_antes", None))
            ahora = promocion.get("precio_ahora", getattr(descuento_actual, "precio_ahora", None))
            if antes is None or ahora is None:
                raise serializers.ValidationError(
                    {"promocion": "Indique el precio anterior y el precio promocional."}
                )
            if ahora > antes:
                raise serializers.ValidationError(
                    {"promocion": "El precio promocional no puede superar al anterior."}
                )
            # El precio de referencia de una oferta nueva debe ser el precio
            # normal vigente. Las ofertas históricas sin cambios se conservan.
            if antes != precio:
                raise serializers.ValidationError(
                    {
                        "promocion": (
                            "El precio anterior debe coincidir con el precio normal de venta."
                        )
                    }
                )
            inicio = promocion.get("fecha_inicio", getattr(descuento_actual, "fecha_inicio", None))
            fin = promocion.get("fecha_fin", getattr(descuento_actual, "fecha_fin", None))
            if inicio and fin and fin < inicio:
                raise serializers.ValidationError({"promocion": "Las fechas no son válidas."})
        return attrs

    @staticmethod
    def _validar_fichas(attrs, instance=None):
        silla = attrs.get("productosilla") or {}
        ficha_silla = getattr(instance, "productosilla", None) if instance else None
        for campo in ("marca", "color_primario", "color_secundario"):
            _validar_valor(
                silla.get(campo),
                "MARCA" if campo == "marca" else "COLOR",
                campo,
                getattr(ficha_silla, campo, None),
            )
        especificaciones = silla.get("especificaciones")
        if especificaciones is not None and not isinstance(especificaciones, dict):
            raise serializers.ValidationError(
                {"silla": "especificaciones debe ser un objeto JSON."}
            )
        piso = attrs.get("productopiso") or {}
        for campo, concepto in {
            "marca": "MARCA",
            "tipo": "TIPO_PISO",
            "material": "MATERIAL_PISO",
            "diseno": "DISENO_PISO",
            "acabado": "ACABADO_PISO",
        }.items():
            ficha_piso = getattr(instance, "productopiso", None) if instance else None
            _validar_valor(
                piso.get(campo),
                concepto,
                campo,
                getattr(ficha_piso, campo, None),
            )
        for campo in ("espesor_mm", "largo_mm", "ancho_mm", "m2_por_caja"):
            if piso.get(campo) is not None and piso[campo] <= 0:
                raise serializers.ValidationError({"piso": f"{campo} debe ser mayor que cero."})

    @transaction.atomic
    def create(self, validated_data):
        silla = validated_data.pop("productosilla", None)
        piso = validated_data.pop("productopiso", None)
        promocion = validated_data.pop("descuentoproducto", None)
        audit = validated_data.pop("revision_humana_voz", [])
        producto = Producto.objects.create(stock=0, **validated_data)
        self._guardar_relaciones(producto, silla, piso, promocion)
        self._guardar_revision_voz(producto, audit)
        return producto

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = Producto.objects.select_for_update().get(pk=instance.pk)
        revision_esperada = self.context["request"].headers.get("If-Match")
        if not revision_esperada:
            raise serializers.ValidationError(
                {"revision_esperada": "Debes cargar la última versión del producto."}
            )
        if revision_esperada != revision_producto(instance):
            raise ConflictoComercial(
                {"revision_esperada": "El producto cambió desde que abriste la ficha."}
            )
        audit = validated_data.pop("revision_humana_voz", [])
        silla = validated_data.pop("productosilla", serializers.empty)
        piso = validated_data.pop("productopiso", serializers.empty)
        promocion = validated_data.pop("descuentoproducto", serializers.empty)
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.save()
        self._guardar_relaciones(instance, silla, piso, promocion)
        self._guardar_revision_voz(instance, audit)
        return instance

    def _guardar_revision_voz(self, producto, audit):
        from apps.capturas.revision_voz import validar_revision_voz

        final = {
            "nombre": producto.nombre,
            "precio_lista": str(producto.precio_lista),
            "unidad_stock": producto.unidad_stock_id,
            "observaciones": producto.observaciones,
        }
        for relation in ("productosilla", "productopiso"):
            ficha = getattr(producto, relation, None)
            if ficha:
                for field in ficha._meta.fields:
                    if field.name not in {"producto", "created_by", "updated_by"}:
                        value = getattr(ficha, field.attname)
                        final[field.name] = str(value) if isinstance(value, Decimal) else value
        producto.revision_humana_voz = validar_revision_voz(
            incoming=audit,
            previous=producto.revision_humana_voz,
            actor=self.context["request"].user,
            mode="CATALOGO_CREACION",
            final=final,
            category=producto.categoria.codigo,
            product_id=producto.pk,
        )
        producto.save(update_fields=["revision_humana_voz"])

    def _guardar_relaciones(self, producto, silla, piso, promocion):
        actor = self.context["request"].user
        for datos, modelo in ((silla, ProductoSilla), (piso, ProductoPiso)):
            if datos is serializers.empty or datos is None:
                continue
            ficha, creada = modelo.objects.get_or_create(
                producto=producto,
                defaults={**datos, "updated_by": actor, "created_by": actor},
            )
            if not creada:
                for campo, valor in datos.items():
                    setattr(ficha, campo, valor)
                ficha.updated_by = actor
                ficha.save()
        if promocion is None:
            DescuentoProducto.objects.filter(producto=producto).delete()
        elif promocion is not serializers.empty:
            descuento, creado = DescuentoProducto.objects.get_or_create(
                producto=producto,
                defaults={**promocion, "updated_by": actor, "created_by": actor},
            )
            if not creado:
                for campo, valor in promocion.items():
                    setattr(descuento, campo, valor)
                descuento.updated_by = actor
                descuento.save()

    def get_demanda_pendiente(self, producto) -> str:
        demanda = getattr(producto, "demanda_pendiente_calculada", None)
        if demanda is None:
            demanda = demanda_pendiente_por_producto(producto.id)
        return str(demanda)

    def get_disponibilidad_referencial(self, producto) -> str:
        demanda = getattr(producto, "demanda_pendiente_calculada", None)
        if demanda is None:
            demanda = demanda_pendiente_por_producto(producto.id)
        return str(producto.stock - demanda)

    def get_estado_stock(self, producto) -> str:
        return estado_stock_producto(producto.stock, producto.stock_minimo)

    @extend_schema_field(ImagenPrincipalSerializer(allow_null=True))
    def get_imagen_principal(self, producto):
        return imagen_principal_publica(producto)

    def get_precio_vigente(self, producto) -> str:
        return str(precio_catalogo_vigente(producto)[1])

    @extend_schema_field(serializers.CharField())
    def get_revision(self, producto) -> str:
        return revision_producto(producto)


class CatalogoOpcionesFiltrosSerializer(serializers.Serializer):
    concepto = serializers.ChoiceField(
        choices=[
            "ESTADO_PROFORMA",
            "MONEDA",
            "TIPO_ITEM",
            "UNIDAD_MEDIDA",
            "TIPO_MUEBLE",
            "TIPO_CLIENTE",
            "ESTADO_PEDIDO",
            "ESTADO_ORDEN_TRABAJO",
            "TIPO_PAGO",
            "TIPO_MOVIMIENTO",
            "CATEGORIA_PRODUCTO",
            "MARCA",
            "COLOR",
            "TIPO_PISO",
            "MATERIAL_PISO",
            "DISENO_PISO",
            "ACABADO_PISO",
        ]
    )


class TipoMuebleCrearSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=150, trim_whitespace=True)

    def validate(self, attrs):
        extras = set(self.initial_data) - {"nombre"}
        if extras:
            raise serializers.ValidationError({campo: "Campo no permitido." for campo in extras})
        return attrs


class TipoMuebleRespuestaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    codigo = serializers.CharField()
    nombre = serializers.CharField()


class TipoMuebleConflictoSerializer(serializers.Serializer):
    codigo = serializers.CharField()
    existente = TipoMuebleRespuestaSerializer()


class AtributoMuebleSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="valor_id")
    codigo = serializers.CharField(source="valor.codigo")
    nombre = serializers.CharField(source="valor.nombre")

    class Meta:
        model = MetadatoAtributoMueble
        fields = ["id", "codigo", "nombre", "grupo", "tipo_entrada", "ambitos", "sinonimos"]


class LimitesConfiguradorSerializer(serializers.Serializer):
    max_conjuntos = serializers.IntegerField()
    max_componentes = serializers.IntegerField()


@extend_schema_serializer(many=False)
class CatalogoAtributosMuebleSerializer(serializers.Serializer):
    limites = LimitesConfiguradorSerializer()
    atributos = AtributoMuebleSerializer(many=True)


class ProductoStockMinimoSerializer(serializers.Serializer):
    stock_minimo = serializers.DecimalField(
        max_digits=14,
        decimal_places=4,
        allow_null=True,
        required=True,
        min_value=Decimal("0"),
    )

    def validate_stock_minimo(self, value):
        producto = self.context.get("producto")
        if value is not None and producto is not None:
            try:
                validar_cantidad_segun_unidad(
                    value,
                    producto.unidad_stock.codigo,
                    permitir_cero=True,
                )
            except serializers.ValidationError as exc:
                raise serializers.ValidationError(exc.detail) from exc
        return value


class EstadoProformaDemandaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    codigo = serializers.CharField()
    nombre = serializers.CharField()


class ProformaDemandaItemSerializer(serializers.Serializer):
    proforma_id = serializers.IntegerField()
    numero = serializers.IntegerField()
    fecha = serializers.DateField()
    estado = EstadoProformaDemandaSerializer()
    cantidad = serializers.CharField()


class DemandaPendienteDesgloseSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    demanda_pendiente_total = serializers.CharField()
    cantidad_restringida = serializers.CharField()
    proformas = ProformaDemandaItemSerializer(many=True)


class ProductoVerificarSimilaresQuerySerializer(serializers.Serializer):
    exclude_id = serializers.IntegerField(required=False, min_value=1)
    sku = serializers.CharField(required=False, allow_blank=True, max_length=80)
    nombre = serializers.CharField(required=False, allow_blank=True, max_length=200)
    categoria = serializers.IntegerField(required=False, min_value=1)
    marca = serializers.IntegerField(required=False, min_value=1)
    modelo = serializers.CharField(required=False, allow_blank=True, max_length=150)
    color_primario = serializers.IntegerField(required=False, min_value=1)
    espesor_mm = serializers.DecimalField(
        required=False, max_digits=8, decimal_places=2, min_value=Decimal("0.01")
    )


class ProductoSimilarItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField(allow_null=True)
    nombre = serializers.CharField()
    categoria_nombre = serializers.CharField()
    precio_vigente = serializers.CharField()
    stock = serializers.CharField()
    unidad_nombre = serializers.CharField()
    activo = serializers.BooleanField()
    coincidencia = serializers.ChoiceField(
        choices=["SKU_EXACTO", "NOMBRE_EXACTO", "ATRIBUTOS_IGUALES", "SIMILAR"]
    )
    motivo = serializers.CharField()


class ProductoSimilaresRespuestaSerializer(serializers.Serializer):
    sku_duplicado = ProductoSimilarItemSerializer(allow_null=True)
    similares = ProductoSimilarItemSerializer(many=True)
