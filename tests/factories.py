from django.contrib.auth.models import Group

from apps.catalogo.models import ConceptoCatalogo, Producto, ProductoSilla, ValorCatalogo
from apps.clientes.models import Cliente

NOMBRES = {
    "TIPO_CLIENTE": {"PERSONA": "Persona natural", "EMPRESA": "Empresa"},
    "TIPO_ITEM": {
        "MUEBLE_MEDIDA": "Mueble a medida",
        "SILLA": "Silla",
        "PISO_FLOTANTE": "Piso flotante",
        "OTRO": "Otro",
    },
    "ESTADO_PROFORMA": {"BORRADOR": "Borrador", "ENVIADA": "Enviada", "APROBADA": "Aprobada"},
    "MONEDA": {"BOB": "Bolivianos", "USD": "Dólares"},
    "UNIDAD_MEDIDA": {"PIEZA": "Pieza", "CAJA": "Caja"},
    "CATEGORIA_PRODUCTO": {"SILLA": "Silla", "PISO_FLOTANTE": "Piso flotante", "OTRO": "Otro"},
    "TIPO_MUEBLE": {"MESA_REUNION": "Mesa de reunión"},
}


def valor(concepto, codigo):
    concepto_objeto, _ = ConceptoCatalogo.objects.get_or_create(codigo=concepto)
    return ValorCatalogo.objects.get_or_create(
        concepto=concepto_objeto, codigo=codigo, defaults={"nombre": NOMBRES[concepto][codigo]}
    )[0]


def vendedor(user):
    grupo, _ = Group.objects.get_or_create(name="VENDEDOR")
    user.groups.add(grupo)
    return user


def cliente_persona(actor, *, sufijo=""):
    return Cliente.objects.create(
        tipo_cliente=valor("TIPO_CLIENTE", "PERSONA"),
        nombres=f"Ana{sufijo}",
        apellidos="López",
        created_by=actor,
        updated_by=actor,
    )


def silla(actor, *, sku="S-1", precio="50.00", stock=0):
    producto = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "SILLA"),
        sku=sku,
        nombre=f"Silla {sku}",
        precio_lista=precio,
        stock=stock,
        unidad_stock=valor("UNIDAD_MEDIDA", "PIEZA"),
        created_by=actor,
        updated_by=actor,
    )
    ProductoSilla.objects.create(producto=producto, created_by=actor, updated_by=actor)
    return producto
