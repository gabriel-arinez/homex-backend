import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Producto, ProductoPiso, ProductoSilla, ValorCatalogo
from apps.movimientos_stock.models import MovimientoStock


class ErrorCatalogo(ValueError):
    pass


@dataclass(frozen=True)
class ResultadoImportacion:
    creados: int
    existentes: int
    movimientos_stock: int


CAMPOS_FICHA_SILLA = {
    "marca",
    "modelo",
    "color_primario",
    "color_secundario",
    "especificaciones",
}

CAMPOS_FICHA_PISO = {
    "marca",
    "modelo",
    "tipo",
    "material",
    "diseno",
    "espesor_mm",
    "acabado",
    "largo_mm",
    "ancho_mm",
    "m2_por_caja",
}


def cargar_archivo_catalogo(ruta: str | Path) -> dict:
    try:
        contenido = Path(ruta).read_text(encoding="utf-8")
        datos = json.loads(contenido)
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorCatalogo(
            "El catálogo debe ser un archivo JSON comercial válido; JSONL NER no es aceptado."
        ) from exc

    if (
        not isinstance(datos, dict)
        or datos.get("schema_version") != 1
        or not isinstance(datos.get("productos"), list)
    ):
        raise ErrorCatalogo(
            "Se requiere JSON comercial schema_version=1; JSONL NER no es un catálogo válido."
        )

    return datos


def _valor(concepto: str, codigo: str) -> ValorCatalogo:
    try:
        return ValorCatalogo.objects.get(
            concepto__codigo=concepto,
            codigo=codigo,
            activo=True,
        )
    except ValorCatalogo.DoesNotExist as exc:
        raise ErrorCatalogo(f"No existe un valor activo {concepto}.{codigo}.") from exc


def _decimal(valor, campo: str) -> Decimal:
    try:
        resultado = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ErrorCatalogo(f"{campo} debe ser un decimal válido.") from exc

    if not resultado.is_finite():
        raise ErrorCatalogo(f"{campo} debe ser un decimal finito.")

    if resultado < 0:
        raise ErrorCatalogo(f"{campo} no puede ser negativo.")

    return resultado


def _decimal_opcional(valor, campo: str) -> Decimal | None:
    if valor in (None, ""):
        return None
    return _decimal(valor, campo)


def _requerir(item: dict, campo: str):
    valor = item.get(campo)

    if valor in (None, ""):
        raise ErrorCatalogo(f"Cada producto requiere {campo}.")

    return valor


def _requerir_ficha(
    ficha: dict,
    campo: str,
    sku: str,
):
    valor = ficha.get(campo)

    if valor in (None, ""):
        raise ErrorCatalogo(f"SKU {sku} requiere ficha.{campo}.")

    return valor


def _validar_campos_ficha(
    *,
    ficha: dict,
    permitidos: set[str],
    sku: str,
) -> None:
    desconocidos = set(ficha) - permitidos

    if desconocidos:
        campos = ", ".join(sorted(desconocidos))
        raise ErrorCatalogo(f"SKU {sku} contiene campos de ficha no soportados: {campos}.")


def _validar_lote(productos: list[dict]) -> None:
    skus = []

    for item in productos:
        if not isinstance(item, dict):
            raise ErrorCatalogo("Cada producto debe ser un objeto JSON.")

        sku = _requerir(item, "sku")
        _requerir(item, "categoria")
        _requerir(item, "nombre")
        _requerir(item, "unidad_stock")
        _requerir(item, "precio_lista")
        _requerir(item, "stock_inicial")

        activo = item.get("activo", True)
        if not isinstance(activo, bool):
            raise ErrorCatalogo(f"SKU {sku}: activo debe ser booleano.")

        skus.append(sku)

    if len(skus) != len(set(skus)):
        raise ErrorCatalogo("El archivo contiene SKU duplicados.")


def _preparar_ficha(
    *,
    sku: str,
    categoria: str,
    ficha,
) -> dict | None:
    if categoria == "SILLA":
        if not isinstance(ficha, dict):
            raise ErrorCatalogo(f"SKU {sku} requiere ficha de silla.")

        _validar_campos_ficha(
            ficha=ficha,
            permitidos=CAMPOS_FICHA_SILLA,
            sku=sku,
        )

        marca = _requerir_ficha(
            ficha,
            "marca",
            sku,
        )
        color_primario = _requerir_ficha(
            ficha,
            "color_primario",
            sku,
        )

        return {
            "marca": _valor("MARCA", marca),
            "modelo": ficha.get("modelo"),
            "color_primario": _valor(
                "COLOR",
                color_primario,
            ),
            "color_secundario": (
                _valor(
                    "COLOR",
                    ficha["color_secundario"],
                )
                if ficha.get("color_secundario")
                else None
            ),
            "especificaciones": ficha.get("especificaciones"),
        }

    if categoria == "PISO_FLOTANTE":
        if not isinstance(ficha, dict):
            raise ErrorCatalogo(f"SKU {sku} requiere ficha de piso.")

        _validar_campos_ficha(
            ficha=ficha,
            permitidos=CAMPOS_FICHA_PISO,
            sku=sku,
        )

        marca = _requerir_ficha(
            ficha,
            "marca",
            sku,
        )
        m2_por_caja = _decimal(
            _requerir_ficha(
                ficha,
                "m2_por_caja",
                sku,
            ),
            "ficha.m2_por_caja",
        )

        if m2_por_caja <= 0:
            raise ErrorCatalogo(f"SKU {sku}: ficha.m2_por_caja debe ser mayor a cero.")

        return {
            "marca": _valor("MARCA", marca),
            "modelo": ficha.get("modelo"),
            "tipo": (_valor("TIPO_PISO", ficha["tipo"]) if ficha.get("tipo") else None),
            "material": (
                _valor(
                    "MATERIAL_PISO",
                    ficha["material"],
                )
                if ficha.get("material")
                else None
            ),
            "diseno": (
                _valor(
                    "DISENO_PISO",
                    ficha["diseno"],
                )
                if ficha.get("diseno")
                else None
            ),
            "espesor_mm": _decimal_opcional(
                ficha.get("espesor_mm"),
                "ficha.espesor_mm",
            ),
            "acabado": (
                _valor(
                    "ACABADO_PISO",
                    ficha["acabado"],
                )
                if ficha.get("acabado")
                else None
            ),
            "largo_mm": _decimal_opcional(
                ficha.get("largo_mm"),
                "ficha.largo_mm",
            ),
            "ancho_mm": _decimal_opcional(
                ficha.get("ancho_mm"),
                "ficha.ancho_mm",
            ),
            "m2_por_caja": m2_por_caja,
        }

    if ficha not in (None, {}):
        raise ErrorCatalogo(f"SKU {sku}: la categoría {categoria} no admite ficha especializada.")

    return None


def _carga_inicial_coincide(
    *,
    producto: Producto,
    stock: int,
) -> bool:
    tipo_carga = _valor(
        "TIPO_MOVIMIENTO",
        "CARGA_INICIAL",
    )

    cargas = MovimientoStock.objects.filter(
        producto=producto,
        tipo_movimiento=tipo_carga,
    )

    if stock == 0:
        return not cargas.exists()

    if cargas.count() != 1:
        return False

    return cargas.get().cantidad == stock


def _ficha_coincide(
    *,
    producto: Producto,
    categoria: str,
    ficha: dict | None,
) -> bool:
    if categoria == "SILLA":
        try:
            existente = producto.productosilla
        except ProductoSilla.DoesNotExist:
            return False

        return (
            existente.marca_id == ficha["marca"].id
            and existente.modelo == ficha["modelo"]
            and existente.color_primario_id == ficha["color_primario"].id
            and existente.color_secundario_id
            == (ficha["color_secundario"].id if ficha["color_secundario"] else None)
            and existente.especificaciones == ficha["especificaciones"]
        )

    if categoria == "PISO_FLOTANTE":
        try:
            existente = producto.productopiso
        except ProductoPiso.DoesNotExist:
            return False

        return (
            existente.marca_id == ficha["marca"].id
            and existente.modelo == ficha["modelo"]
            and existente.tipo_id == (ficha["tipo"].id if ficha["tipo"] else None)
            and existente.material_id == (ficha["material"].id if ficha["material"] else None)
            and existente.diseno_id == (ficha["diseno"].id if ficha["diseno"] else None)
            and existente.espesor_mm == ficha["espesor_mm"]
            and existente.acabado_id == (ficha["acabado"].id if ficha["acabado"] else None)
            and existente.largo_mm == ficha["largo_mm"]
            and existente.ancho_mm == ficha["ancho_mm"]
            and existente.m2_por_caja == ficha["m2_por_caja"]
        )

    return True


def _producto_existente_es_compatible(
    *,
    producto: Producto,
    item: dict,
    categoria: ValorCatalogo,
    unidad: ValorCatalogo,
    precio: Decimal,
    stock: int,
    ficha: dict | None,
) -> bool:
    if producto.categoria_id != categoria.id:
        return False

    if producto.unidad_stock_id != unidad.id:
        return False

    if producto.nombre != item["nombre"]:
        return False

    if producto.precio_lista != precio:
        return False

    if producto.activo != item.get("activo", True):
        return False

    if producto.observaciones != item.get("observaciones"):
        return False

    if not _carga_inicial_coincide(
        producto=producto,
        stock=stock,
    ):
        return False

    return _ficha_coincide(
        producto=producto,
        categoria=categoria.codigo,
        ficha=ficha,
    )


@transaction.atomic
def importar_catalogo(
    *,
    datos: dict,
    actor,
    dry_run: bool = False,
) -> ResultadoImportacion:
    if not isinstance(datos, dict) or datos.get("schema_version") != 1:
        raise ErrorCatalogo("schema_version=1 es obligatorio.")

    productos = datos.get("productos")

    if not isinstance(productos, list):
        raise ErrorCatalogo("productos debe ser una lista.")

    _validar_lote(productos)

    creados = 0
    existentes = 0
    movimientos = 0

    for item in productos:
        sku = item["sku"]

        categoria = _valor(
            "CATEGORIA_PRODUCTO",
            item["categoria"],
        )
        unidad = _valor(
            "UNIDAD_MEDIDA",
            item["unidad_stock"],
        )
        precio = _decimal(
            item["precio_lista"],
            "precio_lista",
        )
        stock_decimal = _decimal(
            item["stock_inicial"],
            "stock_inicial",
        )

        if stock_decimal != stock_decimal.to_integral_value():
            raise ErrorCatalogo("stock_inicial debe ser entero.")

        stock = int(stock_decimal)

        ficha = _preparar_ficha(
            sku=sku,
            categoria=categoria.codigo,
            ficha=item.get("ficha"),
        )

        producto = Producto.objects.select_for_update().filter(sku=sku).first()

        if producto:
            if not _producto_existente_es_compatible(
                producto=producto,
                item=item,
                categoria=categoria,
                unidad=unidad,
                precio=precio,
                stock=stock,
                ficha=ficha,
            ):
                raise ErrorCatalogo(f"SKU {sku} ya existe con datos comerciales distintos.")

            existentes += 1
            continue

        producto = Producto.objects.create(
            categoria=categoria,
            sku=sku,
            nombre=item["nombre"],
            precio_lista=precio,
            stock=0,
            unidad_stock=unidad,
            activo=item.get("activo", True),
            observaciones=item.get("observaciones"),
            created_by=actor,
            updated_by=actor,
        )

        if categoria.codigo == "SILLA":
            ProductoSilla.objects.create(
                producto=producto,
                marca=ficha["marca"],
                modelo=ficha["modelo"],
                color_primario=ficha["color_primario"],
                color_secundario=ficha["color_secundario"],
                especificaciones=ficha["especificaciones"],
                created_by=actor,
                updated_by=actor,
            )

        elif categoria.codigo == "PISO_FLOTANTE":
            ProductoPiso.objects.create(
                producto=producto,
                marca=ficha["marca"],
                modelo=ficha["modelo"],
                tipo=ficha["tipo"],
                material=ficha["material"],
                diseno=ficha["diseno"],
                espesor_mm=ficha["espesor_mm"],
                acabado=ficha["acabado"],
                largo_mm=ficha["largo_mm"],
                ancho_mm=ficha["ancho_mm"],
                m2_por_caja=ficha["m2_por_caja"],
                created_by=actor,
                updated_by=actor,
            )

        if stock:
            MovimientoStock.objects.create(
                producto=producto,
                fecha=timezone.now(),
                tipo_movimiento=_valor(
                    "TIPO_MOVIMIENTO",
                    "CARGA_INICIAL",
                ),
                cantidad=stock,
                observaciones=("Carga inicial por importación de catálogo"),
                created_by=actor,
            )
            movimientos += 1

        creados += 1

    resultado = ResultadoImportacion(
        creados=creados,
        existentes=existentes,
        movimientos_stock=movimientos,
    )

    if dry_run:
        transaction.set_rollback(True)

    return resultado
