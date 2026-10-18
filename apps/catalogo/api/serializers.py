from decimal import Decimal

from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogo.models import (
    DescuentoProducto,
    FamiliaProducto,
    Producto,
    ProductoPiso,
    ProductoSilla,
    ValorCatalogo,
)
from apps.catalogo.revision import revision_producto
from apps.catalogo.services import (
    demanda_pendiente_por_producto,
    descuento_vigente,
    imagen_principal_publica,
    precio_catalogo_vigente,
)
from apps.core.exceptions import ConflictoComercial


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
    class Meta:
        model = ProductoSilla
        exclude = ["created_by", "updated_by"]
        read_only_fields = ["producto"]


class ProductoPisoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductoPiso
        exclude = ["created_by", "updated_by"]
        read_only_fields = ["producto"]


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
            "demanda_pendiente",
            "disponibilidad_referencial",
            "unidad_stock",
            "unidad_stock_info",
            "activo",
            "observaciones",
            "imagen_principal",
            "silla",
            "piso",
            "promocion",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["stock", "created_by", "updated_by"]
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
        producto = Producto.objects.create(stock=0, **validated_data)
        self._guardar_relaciones(producto, silla, piso, promocion)
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
        silla = validated_data.pop("productosilla", serializers.empty)
        piso = validated_data.pop("productopiso", serializers.empty)
        promocion = validated_data.pop("descuentoproducto", serializers.empty)
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        instance.save()
        self._guardar_relaciones(instance, silla, piso, promocion)
        return instance

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
