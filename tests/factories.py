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
    "ESTADO_PROFORMA": {
        "BORRADOR": "Borrador",
        "ENVIADA": "Enviada histórica",
        "EN_REVISION": "En revisión",
        "NO_CONCRETADA": "No concretada",
        "APROBADA": "Aprobada",
        "ANULADA": "Anulada",
        "VENCIDA": "Vencida",
    },
    "ESTADO_PEDIDO": {
        "CONFIRMADO": "Confirmado",
        "EN_PRODUCCION": "En producción",
        "LISTO_ENTREGA": "Listo para entrega",
        "ENTREGADO": "Entregado",
        "CANCELADO": "Cancelado",
    },
    "ESTADO_ORDEN_TRABAJO": {
        "PENDIENTE": "Pendiente",
        "EN_PROCESO": "En proceso",
        "TERMINADA": "Terminada",
        "CANCELADA": "Cancelada",
    },
    "MONEDA": {"BOB": "Bolivianos", "USD": "Dólares"},
    "TIPO_PAGO": {"EFECTIVO": "Efectivo", "CHEQUE": "Cheque"},
    "UNIDAD_MEDIDA": {
        "PIEZA": "Pieza",
        "CAJA": "Caja histórica",
        "M2": "Metro cuadrado",
        "BARRA": "Barra",
        "JUEGO": "Juego",
    },
    "TIPO_MOVIMIENTO": {
        "VENTA": "Salida por venta asociada a pedido confirmado",
        "CARGA_INICIAL": "Carga inicial de existencias",
        "AJUSTE": "Ajuste de stock positivo o negativo con motivo",
        "REVERSA_VENTA": "Devolución de stock por cancelación de una venta",
    },
    "CATEGORIA_PRODUCTO": {"SILLA": "Silla", "PISO_FLOTANTE": "Piso flotante", "OTRO": "Otro"},
    "TIPO_MUEBLE": {
        "MESA_REUNION": "Mesa de reunión",
        "ESTANTE": "Estante",
        "ESCRITORIO": "Escritorio",
        "CREDENZA": "Credenza",
        "ARCHIVERO": "Archivero",
        "GAVETERO": "Gavetero",
    },
}

ATRIBUTOS_MUEBLE = [
    (
        "CONFIGURACION_FORMA",
        "Configuración / Forma",
        "Forma",
        "texto",
        ["mueble"],
        ["forma", "configuración"],
    ),
    (
        "LADO",
        "Lado",
        "Dimensiones",
        "numero_unidad",
        ["mueble", "componente"],
        ["lado 1", "lado 2"],
    ),
    ("DIAMETRO", "Diámetro", "Dimensiones", "numero_unidad", ["mueble", "componente"], []),
    ("ALTO", "Alto", "Dimensiones", "numero_unidad", ["mueble", "componente"], ["altura"]),
    ("LARGO", "Largo", "Dimensiones", "numero_unidad", ["mueble", "componente"], []),
    (
        "CANTIDAD_CAJONES",
        "Cantidad de cajones",
        "Organización",
        "entero",
        ["componente"],
        ["cajones"],
    ),
    ("ESPESOR_TAPA", "Espesor de tapa", "Materiales", "numero_unidad", ["componente"], ["tapa"]),
    (
        "ESPESOR_LATERALES",
        "Espesor de laterales",
        "Materiales",
        "numero_unidad",
        ["componente"],
        ["laterales"],
    ),
    ("MATERIAL", "Material", "Materiales", "texto", ["mueble", "componente"], []),
    ("REVESTIMIENTO", "Revestimiento", "Acabados", "texto", ["componente"], ["melamina"]),
    ("TAPACANTO", "Tapacanto", "Acabados", "texto", ["componente"], ["canto"]),
    ("FIJACION", "Fijación", "Herrajes", "texto", ["componente"], ["unión"]),
    ("PASO_CABLES", "Paso de cables", "Funcionalidad", "texto", ["componente"], ["cableado"]),
    ("TRATAMIENTO", "Tratamiento", "Acabados", "texto", ["componente"], ["anticorrosivo"]),
    ("ACABADO", "Acabado", "Acabados", "texto", ["mueble", "componente"], ["pintura"]),
    (
        "SISTEMA_CIERRE",
        "Sistema de cierre",
        "Herrajes",
        "texto",
        ["componente"],
        ["cerradura", "llave"],
    ),
    ("APERTURA_CAJONES", "Apertura de cajones", "Herrajes", "texto", ["componente"], ["jalador"]),
    (
        "DESLIZAMIENTO_RIELES",
        "Deslizamiento / Rieles",
        "Herrajes",
        "texto",
        ["componente"],
        ["rieles", "correderas"],
    ),
    ("NUMERO_PUERTAS", "Número de puertas", "Organización", "entero", ["componente"], ["puertas"]),
    ("REPISAS", "Repisas", "Organización", "texto", ["componente"], ["estantes"]),
    ("TAPIZADO", "Tapizado", "Textiles", "texto", ["componente"], ["tela"]),
    ("RELLENO", "Relleno", "Textiles", "texto", ["componente"], ["espuma"]),
    (
        "POSICION_ORIENTACION",
        "Posición / Orientación",
        "Forma",
        "texto",
        ["mueble", "componente"],
        ["izquierda", "derecha"],
    ),
]


def sembrar_atributos_mueble():
    from apps.catalogo.models import ConceptoCatalogo, MetadatoAtributoMueble, ValorCatalogo

    concepto, _ = ConceptoCatalogo.objects.get_or_create(
        codigo="ATRIBUTO_MUEBLE",
        defaults={"descripcion": "Definiciones de campos técnicos para muebles", "activo": True},
    )
    for codigo, nombre, grupo, tipo, ambitos, sinonimos in ATRIBUTOS_MUEBLE:
        valor_obj, _ = ValorCatalogo.objects.get_or_create(
            concepto=concepto,
            codigo=codigo,
            defaults={"nombre": nombre, "activo": True},
        )
        MetadatoAtributoMueble.objects.get_or_create(
            valor=valor_obj,
            defaults={
                "grupo": grupo,
                "tipo_entrada": tipo,
                "ambitos": ambitos,
                "sinonimos": sinonimos,
            },
        )


def valor(concepto, codigo):
    concepto_objeto, _ = ConceptoCatalogo.objects.get_or_create(codigo=concepto)
    return ValorCatalogo.objects.get_or_create(
        concepto=concepto_objeto, codigo=codigo, defaults={"nombre": NOMBRES[concepto][codigo]}
    )[0]


def encargado_tienda(user):
    grupo, _ = Group.objects.get_or_create(name="ENCARGADO_TIENDA")
    user.groups.add(grupo)
    return user


def vendedor(user):
    return encargado_tienda(user)


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


def cargar_stock(producto, actor, cantidad):
    from django.utils import timezone

    from apps.movimientos_stock.models import MovimientoStock

    return MovimientoStock.objects.create(
        producto=producto,
        tipo_movimiento=valor("TIPO_MOVIMIENTO", "CARGA_INICIAL"),
        cantidad=cantidad,
        fecha=timezone.now(),
        created_by=actor,
    )


def commercial_voice_text(text):
    """Operationally sufficient fixture without adding commercial attributes."""
    return text + "\n" + " ".join(["detalle"] * 20)


def commercial_voice_audio():
    """A complete fifteen-second PCM fixture for pre-queue audio validation."""
    import io
    import wave

    from django.core.files.uploadedfile import SimpleUploadedFile

    data = io.BytesIO()
    with wave.open(data, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 15)
    return SimpleUploadedFile("voice.wav", data.getvalue(), content_type="audio/wav")
