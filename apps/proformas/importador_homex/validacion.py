"""Validación estructural, de esquema, integridad y reglas para perfiles HOMEX."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from apps.proformas.importador_homex.excepciones import ErrorImportacionHomex
from apps.proformas.importador_homex.seguridad_zip import PaqueteMaestroHomex

TIPOS_EVENTO_VALIDOS = {
    "CREAR_BORRADOR",
    "ENVIAR_PROFORMA",
    "APROBAR_PROFORMA",
    "EMITIR_RECIBO",
    "ANULAR_PROFORMA",
    "EN_PRODUCCION",
    "MARCAR_NO_CONCRETADA",
    "CANCELAR_PEDIDO",
    "LISTO_ENTREGA",
    "ENTREGADO",
    "VENCER_PROFORMA",
}

CATEGORIAS_VALIDAS = {"SILLA", "PISO_FLOTANTE", "OTRO"}
UNIDADES_VALIDAS = {"PIEZA", "M2", "CAJA", "BARRA", "JUEGO"}
MODALIDADES_VALIDAS = {"CON_STOCK", "BAJO_PEDIDO"}


@dataclass(frozen=True)
class ResultadoValidacionDocumental:
    resumen_manifiestos: dict
    total_incidencias: int
    incidencias_por_estado: dict[str, int]
    incidencias_pendientes: list[dict]
    imagenes_verificadas: int
    imagenes_pendientes: list[str]
    productos_candidatos: int
    clientes_candidatos: int
    proformas_grupos: int
    proformas_autorizadas: int
    notas_documentales: int
    notas_autorizadas: int
    reglas_importacion: dict


@dataclass(frozen=True)
class ResultadoValidacionEscenario:
    version: str
    resumen_manifiestos: dict
    catalogo: list[dict]
    clientes: list[dict]
    plantillas: list[dict]
    proformas: list[dict]
    eventos: list[dict]
    pedidos_objetivo: list[dict]
    ordenes_trabajo_objetivo: list[dict]
    recibos_objetivo: list[dict]
    notas_entrega_objetivo: list[dict]
    movimientos_esperados: list[dict]
    conciliacion_stock: list[dict]
    resumen_validacion: dict
    apertura_stock_esperada: list[dict]
    asociaciones_imagenes: list[dict]
    metadatos_procedencia: dict
    revision_clientes_documentales: dict


def parsear_decimal(valor, campo: str) -> Decimal:
    try:
        dec = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ErrorImportacionHomex(f"{campo} debe ser un decimal válido ({valor!r}).") from exc
    if not dec.is_finite():
        raise ErrorImportacionHomex(f"{campo} debe ser un decimal finito.")
    return dec


def parsear_fecha(valor, campo: str) -> date:
    if not isinstance(valor, str):
        raise ErrorImportacionHomex(f"{campo} debe ser una fecha ISO YYYY-MM-DD.")
    try:
        return date.fromisoformat(valor)
    except ValueError as exc:
        raise ErrorImportacionHomex(f"{campo} inválida ({valor!r}).") from exc


def parsear_fecha_hora(valor, campo: str) -> datetime:
    if not isinstance(valor, str):
        raise ErrorImportacionHomex(f"{campo} debe ser un timestamp ISO 8601.")
    try:
        return datetime.fromisoformat(valor)
    except ValueError as exc:
        raise ErrorImportacionHomex(f"{campo} inválido ({valor!r}).") from exc


def validar_paquete_documental(paquete: PaqueteMaestroHomex) -> ResultadoValidacionDocumental:
    """Valida el perfil documental, sus 71 incidencias pendientes e imágenes candidatas."""
    resumen_manifiestos = paquete.verificar_manifiestos(perfil="documental")

    reglas = paquete.leer_json("11_resolucion/reglas_importacion.json")
    incidencias = paquete.leer_json("11_resolucion/incidencias_decisiones.json")
    productos = paquete.leer_json("11_resolucion/productos_decisiones.json")
    clientes = paquete.leer_json("11_resolucion/clientes_decisiones.json")
    proformas = paquete.leer_json("11_resolucion/proformas_decisiones.json")
    notas = paquete.leer_json("11_resolucion/notas_decisiones.json")
    imagenes_mapeo = paquete.leer_json("01_catalogo/imagenes_mapeo.json")

    for nombre, coleccion in (
        ("incidencias_decisiones.json", incidencias),
        ("productos_decisiones.json", productos),
        ("clientes_decisiones.json", clientes),
        ("proformas_decisiones.json", proformas),
        ("notas_decisiones.json", notas),
        ("imagenes_mapeo.json", imagenes_mapeo),
    ):
        if not isinstance(coleccion, list):
            raise ErrorImportacionHomex(f"{nombre} debe ser una lista JSON.")

    imagenes_pendientes: list[str] = []
    for img in imagenes_mapeo:
        archivo = img.get("archivo")
        sha_esperado = img.get("sha256")
        if not archivo or not sha_esperado:
            raise ErrorImportacionHomex(f"Entrada de imagen incompleta: {img}")
        ruta_img = f"01_catalogo/{archivo}"
        sha_actual = paquete.sha256(ruta_img)
        if sha_actual != sha_esperado:
            raise ErrorImportacionHomex(
                f"SHA-256 inválido para imagen {ruta_img}: {sha_actual} != {sha_esperado}"
            )
        if img.get("estado") != "VALIDADA":
            imagenes_pendientes.append(archivo)

    estados_inc = Counter(item.get("estado_resolucion") for item in incidencias)
    pendientes = [
        {
            "id_incidencia": item.get("id_incidencia"),
            "id_fuente": item.get("id_fuente"),
            "codigo": item.get("codigo"),
            "nivel": item.get("nivel"),
            "detalle": item.get("detalle"),
            "decision": item.get("decision"),
        }
        for item in incidencias
        if item.get("estado_resolucion") == "PENDIENTE_VALIDACION"
    ]

    proformas_autorizadas = sum(
        1 for item in proformas if item.get("importacion_operativa_autorizada") is True
    )
    notas_autorizadas = sum(
        1 for item in notas if item.get("crear_pedido_o_nota_operativa") is True
    )

    return ResultadoValidacionDocumental(
        resumen_manifiestos=resumen_manifiestos,
        total_incidencias=len(incidencias),
        incidencias_por_estado=dict(estados_inc),
        incidencias_pendientes=pendientes,
        imagenes_verificadas=len(imagenes_mapeo),
        imagenes_pendientes=imagenes_pendientes,
        productos_candidatos=len(productos),
        clientes_candidatos=len(clientes),
        proformas_grupos=len(proformas),
        proformas_autorizadas=proformas_autorizadas,
        notas_documentales=len(notas),
        notas_autorizadas=notas_autorizadas,
        reglas_importacion=reglas if isinstance(reglas, dict) else {},
    )


def validar_paquete_escenario(paquete: PaqueteMaestroHomex) -> ResultadoValidacionEscenario:
    """Valida integridad SHA-256, esquemas, relaciones y aritmética de 12_escenario_evaluacion."""
    resumen_manifiestos = paquete.verificar_manifiestos(perfil="escenario")
    version = str(resumen_manifiestos.get("version_escenario") or "0.5")

    catalogo = paquete.leer_json("12_escenario_evaluacion/catalogo_escenario.json")
    clientes = paquete.leer_json("12_escenario_evaluacion/clientes_ficticios.json")
    plantillas = paquete.leer_json("12_escenario_evaluacion/plantillas_mueble.json")
    proformas = paquete.leer_json("12_escenario_evaluacion/proformas.json")
    eventos = paquete.leer_json("12_escenario_evaluacion/eventos_cronologicos.json")
    pedidos_obj = paquete.leer_json("12_escenario_evaluacion/pedidos_objetivo.json")
    ot_obj = paquete.leer_json("12_escenario_evaluacion/ordenes_trabajo_objetivo.json")
    recibos_obj = paquete.leer_json("12_escenario_evaluacion/recibos_objetivo.json")
    notas_obj = paquete.leer_json("12_escenario_evaluacion/notas_entrega_objetivo.json")
    movs_esp = paquete.leer_json("12_escenario_evaluacion/movimientos_esperados.json")
    conc_stock = paquete.leer_json("12_escenario_evaluacion/conciliacion_stock.json")
    resumen_val = paquete.leer_json("12_escenario_evaluacion/resumen_validacion.json")

    apertura_stock = (
        paquete.leer_json("12_escenario_evaluacion/apertura_stock_esperada.json")
        if version in {"0.6", "0.7"}
        else []
    )
    asoc_imagenes = (
        paquete.leer_json("12_escenario_evaluacion/asociaciones_imagenes_v06.json")
        if version in {"0.6", "0.7"}
        else []
    )
    meta_proc = (
        paquete.leer_json("12_escenario_evaluacion/metadatos_procedencia_v06.json")
        if version in {"0.6", "0.7"}
        else {}
    )
    rev_doc_cli = (
        paquete.leer_json("12_escenario_evaluacion/revision_clientes_documentales.json")
        if version in {"0.6", "0.7"}
        else {}
    )

    if version in {"0.6", "0.7"}:
        if rev_doc_cli.get("importacion_operativa_autorizada") is not False:
            raise ErrorImportacionHomex(
                "revision_clientes_documentales.json debe mantener "
                "importacion_operativa_autorizada=false."
            )
        for img in asoc_imagenes:
            if img.get("asignacion_automatica_propuesta") is True:
                ruta_img = img.get("ruta_paquete")
                sha_esp = img.get("sha256")
                if not ruta_img or not sha_esp:
                    raise ErrorImportacionHomex(f"Imagen autorizada incompleta: {img}")
                sha_act = paquete.sha256(ruta_img)
                if sha_act != sha_esp:
                    raise ErrorImportacionHomex(
                        f"SHA-256 inválido para imagen {ruta_img}: {sha_act} != {sha_esp}"
                    )

    for nombre, col in (
        ("catalogo_escenario.json", catalogo),
        ("clientes_ficticios.json", clientes),
        ("plantillas_mueble.json", plantillas),
        ("proformas.json", proformas),
        ("eventos_cronologicos.json", eventos),
        ("pedidos_objetivo.json", pedidos_obj),
        ("ordenes_trabajo_objetivo.json", ot_obj),
        ("recibos_objetivo.json", recibos_obj),
        ("notas_entrega_objetivo.json", notas_obj),
        ("movimientos_esperados.json", movs_esp),
        ("conciliacion_stock.json", conc_stock),
    ):
        if not isinstance(col, list):
            raise ErrorImportacionHomex(f"{nombre} debe ser una lista JSON.")
    if not isinstance(resumen_val, dict):
        raise ErrorImportacionHomex("resumen_validacion.json debe ser un objeto JSON.")

    skus_vistos: dict[str, dict] = {}
    for prod in catalogo:
        sku = prod.get("sku")
        if not sku or not isinstance(sku, str):
            raise ErrorImportacionHomex(f"Producto sin SKU válido: {prod}")
        if sku in skus_vistos:
            raise ErrorImportacionHomex(f"SKU duplicado en catalogo_escenario.json: {sku}")
        cat = prod.get("categoria")
        uni = prod.get("unidad_stock")
        mod = prod.get("modalidad_abastecimiento")
        if cat not in CATEGORIAS_VALIDAS:
            raise ErrorImportacionHomex(f"Categoría inválida para {sku}: {cat}")
        if uni not in UNIDADES_VALIDAS:
            raise ErrorImportacionHomex(f"Unidad inválida para {sku}: {uni}")
        if mod not in MODALIDADES_VALIDAS:
            raise ErrorImportacionHomex(f"Modalidad inválida para {sku}: {mod}")
        precio = parsear_decimal(prod.get("precio_lista"), f"{sku}.precio_lista")
        stock = parsear_decimal(prod.get("stock_inicial"), f"{sku}.stock_inicial")
        if precio < 0 or stock < 0:
            raise ErrorImportacionHomex(f"Precio o stock negativo en {sku}.")
        if mod == "BAJO_PEDIDO" and stock != 0:
            raise ErrorImportacionHomex(
                f"Producto BAJO_PEDIDO {sku} no puede tener stock_inicial > 0."
            )
        if uni != "M2" and stock != stock.to_integral_value():
            raise ErrorImportacionHomex(f"Stock no entero para unidad {uni} en {sku}: {stock}")
        skus_vistos[sku] = prod

    clientes_vistos: set[str] = set()
    empresas_sin_contacto: list[str] = []
    for cli in clientes:
        cid = cli.get("id")
        if not cid or not isinstance(cid, str):
            raise ErrorImportacionHomex(f"Cliente sin id válido: {cli}")
        if cid in clientes_vistos:
            raise ErrorImportacionHomex(f"Cliente duplicado: {cid}")
        tipo_cli = cli.get("tipo_cliente")
        if tipo_cli not in {"PERSONA", "EMPRESA"}:
            raise ErrorImportacionHomex(f"tipo_cliente inválido en {cid}: {tipo_cli}")
        if tipo_cli == "EMPRESA":
            if not (cli.get("empresa") or "").strip():
                raise ErrorImportacionHomex(f"Cliente EMPRESA sin razón social: {cid}")
            if not (cli.get("nombres") or "").strip() or not (cli.get("apellidos") or "").strip():
                empresas_sin_contacto.append(cid)
        else:
            if not (cli.get("nombres") or "").strip() or not (cli.get("apellidos") or "").strip():
                raise ErrorImportacionHomex(f"Cliente PERSONA sin nombres/apellidos: {cid}")
            if (cli.get("empresa") or "").strip():
                raise ErrorImportacionHomex(f"Cliente PERSONA no debe registrar empresa: {cid}")
        clientes_vistos.add(cid)

    if empresas_sin_contacto:
        raise ErrorImportacionHomex(
            "Inconsistencia en 12_escenario_evaluacion/clientes_ficticios.json: "
            f"{len(empresas_sin_contacto)} clientes EMPRESA sin nombres/apellidos de contacto "
            f"(trigger fn_validar_cliente): {', '.join(empresas_sin_contacto)}. "
            "Corrección propuesta: completar nombres y apellidos de contacto ficticio en "
            "clientes_ficticios.json y actualizar su SHA-256 en manifiesto_escenario.json."
        )

    proformas_vistas: set[str] = set()
    for pf in proformas:
        pf_id = pf.get("id")
        if not pf_id or not isinstance(pf_id, str):
            raise ErrorImportacionHomex(f"Proforma sin id válido: {pf}")
        if pf_id in proformas_vistas:
            raise ErrorImportacionHomex(f"Proforma duplicada: {pf_id}")
        proformas_vistas.add(pf_id)

        cid = pf.get("cliente_id")
        if cid not in clientes_vistos:
            raise ErrorImportacionHomex(f"Proforma {pf_id} referencia cliente inexistente: {cid}")
        parsear_fecha(pf.get("fecha"), f"{pf_id}.fecha")
        lineas = pf.get("lineas")
        if not isinstance(lineas, list) or not lineas:
            raise ErrorImportacionHomex(f"Proforma {pf_id} no tiene líneas.")

        suma_subtotal = Decimal("0.00")
        suma_desc = Decimal("0.00")
        suma_total = Decimal("0.00")
        skus_en_pf: set[str] = set()
        for idx, linea in enumerate(lineas, start=1):
            sku = linea.get("sku")
            if sku is not None:
                if sku not in skus_vistos:
                    raise ErrorImportacionHomex(
                        f"Proforma {pf_id} línea {idx} referencia SKU inexistente: {sku}"
                    )
                if sku in skus_en_pf:
                    raise ErrorImportacionHomex(
                        f"Proforma {pf_id} repite SKU {sku} en múltiples líneas."
                    )
                skus_en_pf.add(sku)
            cant = parsear_decimal(linea.get("cantidad"), f"{pf_id}.L{idx}.cantidad")
            pu = parsear_decimal(linea.get("precio_unitario"), f"{pf_id}.L{idx}.precio_unitario")
            desc = parsear_decimal(linea.get("descuento", "0.00"), f"{pf_id}.L{idx}.descuento")
            tot = parsear_decimal(linea.get("total"), f"{pf_id}.L{idx}.total")
            if cant <= 0 or pu <= 0 or desc < 0:
                raise ErrorImportacionHomex(f"Importes/cantidades inválidas en {pf_id}.L{idx}.")
            bruto = (cant * pu).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            esperado = bruto - desc
            if esperado != tot:
                raise ErrorImportacionHomex(
                    f"Total de línea inconsistente en {pf_id}.L{idx}: {tot} != {esperado}"
                )
            suma_subtotal += bruto
            suma_desc += desc
            suma_total += tot

        if parsear_decimal(pf.get("subtotal"), f"{pf_id}.subtotal") != suma_subtotal:
            raise ErrorImportacionHomex(f"Subtotal inconsistente en {pf_id}.")
        if parsear_decimal(pf.get("descuento_total"), f"{pf_id}.descuento_total") != suma_desc:
            raise ErrorImportacionHomex(f"Descuento total inconsistente en {pf_id}.")
        if parsear_decimal(pf.get("total"), f"{pf_id}.total") != suma_total:
            raise ErrorImportacionHomex(f"Total inconsistente en {pf_id}.")

    ordenes_vistos: set[int] = set()
    eventos_ids: set[str] = set()
    for ev in eventos:
        ev_id = ev.get("id")
        if not ev_id or ev_id in eventos_ids:
            raise ErrorImportacionHomex(f"ID de evento inválido o duplicado: {ev_id}")
        eventos_ids.add(ev_id)
        tipo = ev.get("tipo")
        if tipo not in TIPOS_EVENTO_VALIDOS:
            raise ErrorImportacionHomex(f"Tipo de evento desconocido en {ev_id}: {tipo}")
        if ev.get("proforma_id") not in proformas_vistas:
            raise ErrorImportacionHomex(
                f"Evento {ev_id} referencia proforma inexistente: {ev.get('proforma_id')}"
            )
        parsear_fecha(ev.get("fecha"), f"{ev_id}.fecha")
        orden = ev.get("orden_ejecucion")
        if not isinstance(orden, int) or orden < 1 or orden in ordenes_vistos:
            raise ErrorImportacionHomex(f"orden_ejecucion inválido o duplicado en {ev_id}: {orden}")
        ordenes_vistos.add(orden)

    return ResultadoValidacionEscenario(
        version=version,
        resumen_manifiestos=resumen_manifiestos,
        catalogo=catalogo,
        clientes=clientes,
        plantillas=plantillas,
        proformas=proformas,
        eventos=sorted(eventos, key=lambda item: item["orden_ejecucion"]),
        pedidos_objetivo=pedidos_obj,
        ordenes_trabajo_objetivo=ot_obj,
        recibos_objetivo=recibos_obj,
        notas_entrega_objetivo=notas_obj,
        movimientos_esperados=movs_esp,
        conciliacion_stock=conc_stock,
        resumen_validacion=resumen_val,
        apertura_stock_esperada=apertura_stock,
        asociaciones_imagenes=asoc_imagenes,
        metadatos_procedencia=meta_proc,
        revision_clientes_documentales=rev_doc_cli,
    )
