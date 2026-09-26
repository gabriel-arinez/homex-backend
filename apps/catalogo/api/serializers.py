from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogo.models import (
    DescuentoProducto,
    Producto,
    ProductoPiso,
    ProductoSilla,
    ValorCatalogo,
)
from apps.catalogo.services import (
    demanda_pendiente_por_producto,
    imagen_principal_publica,
    precio_catalogo_vigente,
)


class ProductoSillaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductoSilla
        exclude = ["created_by", "updated_by"]


class ProductoPisoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductoPiso
        exclude = ["created_by", "updated_by"]


class DescuentoProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = DescuentoProducto
        exclude = ["created_by", "updated_by"]


class ImagenPrincipalSerializer(serializers.Serializer):
    original = serializers.URLField()
    ancho = serializers.IntegerField()
    alto = serializers.IntegerField()
    variantes = serializers.DictField(child=serializers.URLField())


class CargaImagenSerializer(serializers.Serializer):
    archivo = serializers.ImageField()


class ProductoFiltrosListadoSerializer(serializers.Serializer):
    activo = serializers.BooleanField(required=False)
    categoria = serializers.IntegerField(required=False, min_value=1)


class ProductoSerializer(serializers.ModelSerializer):
    demanda_pendiente = serializers.SerializerMethodField()
    disponibilidad_referencial = serializers.SerializerMethodField()
    precio_vigente = serializers.SerializerMethodField()
    imagen_principal = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = [
            "id",
            "categoria",
            "sku",
            "nombre",
            "precio_lista",
            "precio_vigente",
            "stock",
            "demanda_pendiente",
            "disponibilidad_referencial",
            "unidad_stock",
            "activo",
            "observaciones",
            "imagen_principal",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["stock", "created_by", "updated_by"]

    def get_demanda_pendiente(self, producto) -> int:
        return demanda_pendiente_por_producto(producto.id)

    def get_disponibilidad_referencial(self, producto) -> int:
        return producto.stock - self.get_demanda_pendiente(producto)

    @extend_schema_field(ImagenPrincipalSerializer(allow_null=True))
    def get_imagen_principal(self, producto):
        return imagen_principal_publica(producto)

    def get_precio_vigente(self, producto) -> str:
        return precio_catalogo_vigente(producto)[1]


class CatalogoOpcionesFiltrosSerializer(serializers.Serializer):
    concepto = serializers.ChoiceField(
        choices=[
            "ESTADO_PROFORMA",
            "MONEDA",
            "TIPO_ITEM",
            "UNIDAD_MEDIDA",
            "TIPO_MUEBLE",
            "ESTADO_PEDIDO",
            "ESTADO_ORDEN_TRABAJO",
            "TIPO_PAGO",
            "TIPO_MOVIMIENTO",
        ]
    )


class ValorCatalogoPublicoSerializer(serializers.ModelSerializer):
    concepto_codigo = serializers.CharField(source="concepto.codigo", read_only=True)

    class Meta:
        model = ValorCatalogo
        fields = ["id", "concepto_codigo", "codigo", "nombre"]
        read_only_fields = fields
