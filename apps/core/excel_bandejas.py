"""Exportadores Excel (.xlsx) reutilizables para todas las bandejas HOMEX."""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalogo.models import FamiliaProducto, ValorCatalogo
from apps.clientes.models import Cliente
from apps.core.excel import generar_excel_corporativo, respuesta_excel
from apps.core.serializers import resumen_usuario
from apps.proformas.vigencia import fecha_limite


def _parse_iso_date(raw: str | dt.date | None, field: str) -> dt.date | None:
    if raw is None:
        return None
    if isinstance(raw, dt.date):
        return raw
    texto = str(raw).strip()
    if not texto:
        return None
    try:
        return dt.date.fromisoformat(texto)
    except ValueError as exc:
        raise ValidationError({field: "Ingresa una fecha válida (YYYY-MM-DD)."}) from exc


def validar_rango_fechas(
    fecha_desde_raw: str | dt.date | None,
    fecha_hasta_raw: str | dt.date | None,
    *,
    max_fecha: dt.date | None = None,
    obligatorio: bool = False,
) -> tuple[dt.date | None, dt.date | None]:
    """Valida formato ISO, orden cronológico y límite superior en America/La_Paz."""
    desde = _parse_iso_date(fecha_desde_raw, "fecha_desde")
    hasta = _parse_iso_date(fecha_hasta_raw, "fecha_hasta")
    if obligatorio:
        if desde is None:
            raise ValidationError({"fecha_desde": "La fecha inicial es obligatoria para exportar."})
        if hasta is None:
            raise ValidationError({"fecha_hasta": "La fecha final es obligatoria para exportar."})
    limite = max_fecha or timezone.localdate()
    if desde and desde > limite:
        raise ValidationError({"fecha_desde": "La fecha no puede ser futura."})
    if hasta and hasta > limite:
        raise ValidationError({"fecha_hasta": "La fecha no puede ser futura."})
    if desde and hasta and desde > hasta:
        raise ValidationError(
            {"fecha_desde": "La fecha inicial no puede ser posterior a la fecha final."}
        )
    return desde, hasta


def slug_segment(valor, max_len: int = 40) -> str:
    if valor is None:
        return ""
    normalizado = (
        unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode("ascii").lower()
    )
    limpio = re.sub(r"[^a-z0-9]+", "-", normalizado).strip("-")
    return limpio[:max_len].rstrip("-")


def construir_nombre_exportacion(
    prefijo: str,
    segmentos: list[object],
    extension: str = "xlsx",
) -> str:
    limpios = [slug_segment(s) for s in segmentos]
    limpios = [s for s in limpios if s]
    base = "_".join([slug_segment(prefijo) or "documento", *limpios])
    ext = extension.lstrip(".").lower()
    return f"{base}.{ext}"


def _nombre_valor_catalogo(raw: str | None, *, grupo: str | None = None) -> str:
    texto = (raw or "").strip()
    if not texto:
        return ""
    qs = ValorCatalogo.objects.all()
    if grupo:
        qs = qs.filter(concepto__codigo=grupo)
    if texto.isdigit():
        obj = qs.filter(pk=int(texto)).first()
    else:
        obj = qs.filter(codigo__iexact=texto).first()
    return obj.nombre if obj else texto


def _nombre_familia(raw: str | None) -> str:
    texto = (raw or "").strip()
    if not texto:
        return ""
    if texto.isdigit():
        obj = FamiliaProducto.objects.filter(pk=int(texto)).first()
        return obj.nombre if obj else texto
    return texto


def _nombre_cliente_filtro(raw: str | None) -> str:
    texto = (raw or "").strip()
    if not texto or not texto.isdigit():
        return texto
    cli = Cliente.objects.filter(pk=int(texto)).first()
    if not cli:
        return texto
    nombre = " ".join(p.strip() for p in [cli.nombres or "", cli.apellidos or ""] if p.strip())
    return cli.empresa or nombre or texto


def _subtitulo_filtros_valores(pares: list[tuple[str, str]]) -> str:
    partes = [f"{etiqueta}: {valor}" for etiqueta, valor in pares if valor]
    return "   |   ".join(partes) if partes else "Filtros: Ninguno (listado completo)"


def _subtitulo_filtros(query_params, etiquetas: dict[str, str]) -> str:
    pares = []
    for clave, etiqueta in etiquetas.items():
        valor = (query_params.get(clave) or "").strip()
        if valor:
            pares.append((etiqueta, valor))
    return _subtitulo_filtros_valores(pares)


def _nombre_usuario(user) -> str:
    res = resumen_usuario(user)
    return (res or {}).get("display_name") or ""


def _cliente_proforma(proforma) -> tuple[str, str]:
    cliente = getattr(proforma, "cliente", None)
    nombre_cliente = (
        " ".join(
            p.strip()
            for p in [
                getattr(cliente, "nombres", "") or "",
                getattr(cliente, "apellidos", "") or "",
            ]
            if p.strip()
        )
        if cliente
        else ""
    )
    nombre = proforma.cliente_nombre_snapshot or nombre_cliente or proforma.prospecto_nombre or ""
    empresa = (
        proforma.cliente_empresa_snapshot
        or (getattr(cliente, "empresa", "") if cliente else "")
        or proforma.prospecto_empresa
        or ""
    )
    return nombre, empresa


def exportar_proformas_excel(queryset, query_params):
    desde, hasta = validar_rango_fechas(
        query_params.get("fecha_desde"),
        query_params.get("fecha_hasta"),
        obligatorio=True,
    )
    assert desde is not None and hasta is not None
    queryset = queryset.filter(fecha__range=(desde, hasta))
    estado_raw = (query_params.get("estado") or "").strip()
    estado_lbl = _nombre_valor_catalogo(estado_raw, grupo="ESTADO_PROFORMA")
    cliente_raw = (query_params.get("cliente") or "").strip()
    cliente_lbl = _nombre_cliente_filtro(cliente_raw)
    moneda_lbl = _nombre_valor_catalogo(query_params.get("moneda"), grupo="MONEDA")
    search_raw = (query_params.get("search") or "").strip()
    desde_raw = desde.isoformat()
    hasta_raw = hasta.isoformat()
    orden_raw = (query_params.get("ordering") or query_params.get("orden") or "").strip()

    subtitulo = _subtitulo_filtros_valores(
        [
            ("Búsqueda", search_raw),
            ("Estado", estado_lbl),
            ("Cliente", cliente_lbl),
            ("Moneda", moneda_lbl),
            ("Desde", desde_raw),
            ("Hasta", hasta_raw),
            ("Orden", orden_raw),
        ]
    )
    columnas = [
        "Número",
        "Título",
        "Fecha",
        "Cliente",
        "Empresa",
        "Estado",
        "Moneda",
        "Subtotal",
        "Descuento",
        "Total",
        "Vencimiento",
        "Vendedor",
    ]

    def _filas():
        for p in queryset.select_related("cliente", "vendedor", "estado", "moneda").iterator(
            chunk_size=500
        ):
            nombre_cli, empresa_cli = _cliente_proforma(p)
            venc = (
                fecha_limite(p.fecha, p.validez_oferta)
                if p.fecha and p.validez_oferta and p.validez_oferta > 0
                else None
            )
            yield [
                p.numero,
                p.titulo or "",
                p.fecha,
                nombre_cli,
                empresa_cli,
                p.estado.nombre,
                p.moneda.codigo,
                p.subtotal,
                p.descuento_total,
                p.total,
                venc,
                _nombre_usuario(p.vendedor),
            ]

    contenido = generar_excel_corporativo(
        titulo_hoja="Proformas",
        titulo_reporte="HOMEX — Listado de Proformas",
        subtitulo_filtros=subtitulo,
        columnas=columnas,
        filas=_filas(),
        anchos=[11, 28, 13, 24, 22, 16, 10, 14, 14, 14, 13, 22],
        integer_cols={1},
        currency_cols={8, 9, 10},
        date_cols={3, 11},
    )
    filename = construir_nombre_exportacion(
        "proformas",
        [estado_lbl, cliente_lbl, moneda_lbl, search_raw, desde_raw, "a", hasta_raw],
    )
    return respuesta_excel(contenido=contenido, filename=filename)


_ESTADO_STOCK_LABELS = {
    "BAJO_PEDIDO": "Bajo pedido",
    "SIN_EXISTENCIAS": "Sin existencias",
    "STOCK_BAJO": "Stock bajo",
    "NORMAL": "Normal",
    "SIN_MINIMO": "Sin mínimo",
}


def exportar_productos_excel(queryset, query_params):
    desde, hasta = validar_rango_fechas(
        query_params.get("fecha_desde"),
        query_params.get("fecha_hasta"),
        obligatorio=True,
    )
    assert desde is not None and hasta is not None
    queryset = queryset.filter(
        Q(movimientostock__fecha__date__range=(desde, hasta))
        | Q(proformadetalle__proforma__fecha__range=(desde, hasta))
    ).distinct()
    desde_raw = desde.isoformat()
    hasta_raw = hasta.isoformat()
    activo_raw = (query_params.get("activo") or "").strip().lower()
    activo_lbl = (
        "Activos"
        if activo_raw in {"true", "1", "activos"}
        else ("Inactivos" if activo_raw in {"false", "0", "inactivos"} else "")
    )
    estado_stock_raw = (query_params.get("estado_stock") or "").strip().upper()
    estado_stock_lbl = _ESTADO_STOCK_LABELS.get(estado_stock_raw, estado_stock_raw)
    categoria_lbl = _nombre_valor_catalogo(
        query_params.get("categoria"), grupo="CATEGORIA_PRODUCTO"
    )
    familia_lbl = _nombre_familia(query_params.get("familia"))
    marca_lbl = _nombre_valor_catalogo(query_params.get("marca"))
    color_lbl = _nombre_valor_catalogo(query_params.get("color_primario"))
    tipo_lbl = _nombre_valor_catalogo(query_params.get("tipo"))
    material_lbl = _nombre_valor_catalogo(query_params.get("material"))
    diseno_lbl = _nombre_valor_catalogo(query_params.get("diseno"))
    acabado_lbl = _nombre_valor_catalogo(query_params.get("acabado"))
    unidad_lbl = _nombre_valor_catalogo(query_params.get("unidad_stock"))
    modalidad_raw = (
        (query_params.get("modalidad_abastecimiento") or query_params.get("modalidad") or "")
        .strip()
        .upper()
    )
    modalidad_lbl = (
        "Bajo pedido"
        if modalidad_raw == "BAJO_PEDIDO"
        else ("Con stock" if modalidad_raw == "CON_STOCK" else modalidad_raw)
    )
    modelo_raw = (query_params.get("modelo") or "").strip()
    espesor_raw = (query_params.get("espesor_mm") or "").strip()
    search_raw = (query_params.get("search") or "").strip()

    subtitulo = _subtitulo_filtros_valores(
        [
            ("Búsqueda", search_raw),
            ("Estado", activo_lbl),
            ("Disponibilidad", estado_stock_lbl),
            ("Categoría", categoria_lbl),
            ("Familia", familia_lbl),
            ("Marca", marca_lbl),
            ("Color", color_lbl),
            ("Tipo", tipo_lbl),
            ("Material", material_lbl),
            ("Diseño", diseno_lbl),
            ("Acabado", acabado_lbl),
            ("Unidad", unidad_lbl),
            ("Modalidad", modalidad_lbl),
            ("Modelo", modelo_raw),
            ("Espesor (mm)", espesor_raw),
            ("Desde", desde_raw),
            ("Hasta", hasta_raw),
        ]
    )
    columnas = [
        "SKU",
        "Nombre",
        "Categoría",
        "Familia",
        "Unidad",
        "Existencia",
        "Stock mínimo",
        "Moneda",
        "Precio lista",
        "Modalidad",
        "Estado",
    ]

    def _filas():
        for prod in queryset.select_related("categoria", "familia", "unidad_stock").iterator(
            chunk_size=500
        ):
            modalidad = (
                "Bajo pedido" if prod.modalidad_abastecimiento == "BAJO_PEDIDO" else "Con stock"
            )
            yield [
                prod.sku or "",
                prod.nombre,
                prod.categoria.nombre,
                prod.familia.nombre if prod.familia else "",
                prod.unidad_stock.nombre,
                prod.stock,
                prod.stock_minimo if prod.stock_minimo is not None else "",
                "BOB",
                prod.precio_lista,
                modalidad,
                "Activo" if prod.activo else "Inactivo",
            ]

    contenido = generar_excel_corporativo(
        titulo_hoja="Productos",
        titulo_reporte="HOMEX — Catálogo de Productos",
        subtitulo_filtros=subtitulo,
        columnas=columnas,
        filas=_filas(),
        anchos=[16, 32, 18, 22, 12, 13, 13, 10, 14, 14, 12],
        numeric_cols={6, 7},
        currency_cols={9},
    )
    filename = construir_nombre_exportacion(
        "productos",
        [
            activo_lbl,
            estado_stock_lbl,
            categoria_lbl,
            familia_lbl,
            marca_lbl,
            color_lbl,
            tipo_lbl,
            material_lbl,
            diseno_lbl,
            acabado_lbl,
            unidad_lbl,
            modalidad_lbl,
            modelo_raw,
            f"{espesor_raw}mm" if espesor_raw else "",
            search_raw,
            desde_raw,
            "a",
            hasta_raw,
        ],
    )
    return respuesta_excel(contenido=contenido, filename=filename)


def exportar_pedidos_excel(queryset, query_params):
    desde, hasta = validar_rango_fechas(
        query_params.get("fecha_desde"),
        query_params.get("fecha_hasta"),
        obligatorio=True,
    )
    assert desde is not None and hasta is not None
    queryset = queryset.filter(fecha_confirmacion__date__range=(desde, hasta))
    estado_lbl = _nombre_valor_catalogo(query_params.get("estado"), grupo="ESTADO_PEDIDO")
    search_raw = (query_params.get("search") or "").strip()
    desde_raw = desde.isoformat()
    hasta_raw = hasta.isoformat()
    subtitulo = _subtitulo_filtros_valores(
        [
            ("Búsqueda", search_raw),
            ("Estado", estado_lbl),
            ("Desde", desde_raw),
            ("Hasta", hasta_raw),
        ]
    )
    columnas = [
        "Pedido #",
        "Proforma #",
        "Título",
        "Fecha confirmación",
        "Cliente",
        "Empresa",
        "Estado",
        "Moneda",
        "Total",
        "Entrega programada",
        "Entrega efectiva",
        "Vendedor",
    ]

    def _filas():
        for ped in queryset.select_related(
            "proforma__cliente",
            "proforma__vendedor",
            "proforma__moneda",
            "estado",
            "ordentrabajo",
        ).iterator(chunk_size=500):
            pf = ped.proforma
            nombre_cli, empresa_cli = _cliente_proforma(pf)
            ot = getattr(ped, "ordentrabajo", None)
            yield [
                ped.id,
                pf.numero,
                pf.titulo or "",
                ped.fecha_confirmacion,
                nombre_cli,
                empresa_cli,
                ped.estado.nombre,
                pf.moneda.codigo,
                pf.total,
                getattr(ot, "fecha_entrega", None),
                ped.fecha_entrega_efectiva,
                _nombre_usuario(pf.vendedor),
            ]

    contenido = generar_excel_corporativo(
        titulo_hoja="Pedidos",
        titulo_reporte="HOMEX — Listado de Pedidos",
        subtitulo_filtros=subtitulo,
        columnas=columnas,
        filas=_filas(),
        anchos=[11, 12, 28, 19, 24, 22, 16, 10, 14, 16, 16, 22],
        integer_cols={1, 2},
        currency_cols={9},
        datetime_cols={4},
        date_cols={10, 11},
    )
    filename = construir_nombre_exportacion(
        "pedidos",
        [estado_lbl, search_raw, desde_raw, "a", hasta_raw],
    )
    return respuesta_excel(contenido=contenido, filename=filename)


def exportar_ordenes_trabajo_excel(queryset, query_params):
    """Exporta órdenes de trabajo sin exponer información financiera."""
    desde, hasta = validar_rango_fechas(
        query_params.get("fecha_desde"),
        query_params.get("fecha_hasta"),
        obligatorio=True,
    )
    assert desde is not None and hasta is not None
    queryset = queryset.filter(fecha__range=(desde, hasta))
    estado_lbl = _nombre_valor_catalogo(query_params.get("estado"), grupo="ESTADO_ORDEN_TRABAJO")
    tipo_raw = (query_params.get("tipo") or "").strip().upper()
    tipo_lbl = (
        "Muebles a medida"
        if tipo_raw == "MUEBLE_MEDIDA"
        else ("Catálogo" if tipo_raw == "CATALOGO" else tipo_raw)
    )
    search_raw = (query_params.get("search") or "").strip()
    desde_raw = desde.isoformat()
    hasta_raw = hasta.isoformat()
    subtitulo = _subtitulo_filtros_valores(
        [
            ("Búsqueda", search_raw),
            ("Estado", estado_lbl),
            ("Tipo", tipo_lbl),
            ("Desde", desde_raw),
            ("Hasta", hasta_raw),
        ]
    )
    columnas = [
        "OT #",
        "Pedido #",
        "Proforma #",
        "Título",
        "Fecha",
        "Cliente",
        "Estado OT",
        "Estado pedido",
        "Fecha inicio",
        "Fecha fin",
        "Entrega prevista",
        "Lugar de entrega",
        "Vendedor",
    ]

    def _filas():
        for ot in queryset.select_related(
            "pedido__proforma__cliente",
            "pedido__proforma__vendedor",
            "pedido__estado",
            "estado",
        ).iterator(chunk_size=500):
            pf = ot.pedido.proforma
            nombre_cli, _ = _cliente_proforma(pf)
            yield [
                ot.numero,
                ot.pedido_id,
                pf.numero,
                pf.titulo or "",
                ot.fecha,
                nombre_cli,
                ot.estado.nombre,
                ot.pedido.estado.nombre,
                ot.fecha_inicio,
                ot.fecha_fin,
                ot.fecha_entrega,
                ot.lugar_entrega or "",
                _nombre_usuario(pf.vendedor),
            ]

    contenido = generar_excel_corporativo(
        titulo_hoja="Órdenes de trabajo",
        titulo_reporte="HOMEX — Listado de Órdenes de Trabajo",
        subtitulo_filtros=subtitulo,
        columnas=columnas,
        filas=_filas(),
        anchos=[11, 11, 12, 26, 13, 24, 15, 16, 13, 13, 15, 28, 22],
        integer_cols={1, 2, 3},
        date_cols={5, 9, 10, 11},
    )
    filename = construir_nombre_exportacion(
        "ordenes-trabajo",
        [estado_lbl, tipo_lbl, search_raw, desde_raw, "a", hasta_raw],
    )
    return respuesta_excel(contenido=contenido, filename=filename)


def exportar_notas_entrega_excel(queryset, query_params):
    desde, hasta = validar_rango_fechas(
        query_params.get("fecha_desde"),
        query_params.get("fecha_hasta"),
        obligatorio=True,
    )
    assert desde is not None and hasta is not None
    queryset = queryset.filter(fecha__range=(desde, hasta))
    search_raw = (query_params.get("search") or "").strip()
    desde_raw = desde.isoformat()
    hasta_raw = hasta.isoformat()
    subtitulo = _subtitulo_filtros_valores(
        [
            ("Búsqueda", search_raw),
            ("Desde", desde_raw),
            ("Hasta", hasta_raw),
        ]
    )
    columnas = [
        "Nota #",
        "Pedido #",
        "Proforma #",
        "Fecha",
        "Cliente",
        "Empresa",
        "Moneda",
        "Total",
        "Receptor",
        "Lugar de entrega",
        "Vendedor",
    ]

    def _filas():
        for nota in queryset.select_related(
            "pedido__proforma__cliente",
            "pedido__proforma__moneda",
            "pedido__ordentrabajo",
            "vendedor",
        ).iterator(chunk_size=500):
            pf = nota.pedido.proforma
            nombre_cli, empresa_cli = _cliente_proforma(pf)
            ot = getattr(nota.pedido, "ordentrabajo", None)
            yield [
                nota.numero,
                nota.pedido_id,
                pf.numero,
                nota.fecha,
                nombre_cli,
                empresa_cli,
                pf.moneda.codigo,
                pf.total,
                getattr(ot, "responsable_recepcion", "") or "",
                getattr(ot, "lugar_entrega", "") or "",
                _nombre_usuario(nota.vendedor),
            ]

    contenido = generar_excel_corporativo(
        titulo_hoja="Notas de entrega",
        titulo_reporte="HOMEX — Listado de Notas de Entrega",
        subtitulo_filtros=subtitulo,
        columnas=columnas,
        filas=_filas(),
        anchos=[11, 11, 12, 13, 24, 22, 10, 14, 22, 28, 22],
        integer_cols={1, 2, 3},
        currency_cols={8},
        date_cols={4},
    )
    filename = construir_nombre_exportacion(
        "notas-entrega",
        [search_raw, desde_raw, "a", hasta_raw],
    )
    return respuesta_excel(contenido=contenido, filename=filename)


def exportar_clientes_excel(queryset, query_params):
    desde, hasta = validar_rango_fechas(
        query_params.get("fecha_desde"),
        query_params.get("fecha_hasta"),
        obligatorio=True,
    )
    assert desde is not None and hasta is not None
    queryset = queryset.filter(proforma__fecha__range=(desde, hasta)).distinct()
    desde_raw = desde.isoformat()
    hasta_raw = hasta.isoformat()
    activo_raw = (query_params.get("activo") or "").strip().lower()
    activo_lbl = (
        "Activos"
        if activo_raw in {"true", "1", "activos"}
        else ("Inactivos" if activo_raw in {"false", "0", "inactivos"} else "")
    )
    tipo_lbl = _nombre_valor_catalogo(query_params.get("tipo_cliente"), grupo="TIPO_CLIENTE")
    search_raw = (query_params.get("search") or "").strip()
    subtitulo = _subtitulo_filtros_valores(
        [
            ("Búsqueda", search_raw),
            ("Estado", activo_lbl),
            ("Tipo", tipo_lbl),
            ("Desde", desde_raw),
            ("Hasta", hasta_raw),
        ]
    )
    columnas = [
        "ID",
        "Tipo",
        "Nombre / Contacto",
        "Empresa",
        "Celular",
        "Dirección",
        "Observaciones",
        "Estado",
    ]

    def _filas():
        for cli in queryset.select_related("tipo_cliente").iterator(chunk_size=500):
            nombre = " ".join(
                p.strip() for p in [cli.nombres or "", cli.apellidos or ""] if p.strip()
            )
            yield [
                cli.id,
                cli.tipo_cliente.nombre,
                nombre,
                cli.empresa or "",
                cli.celular or "",
                cli.direccion or "",
                cli.observaciones or "",
                "Activo" if cli.activo else "Inactivo",
            ]

    contenido = generar_excel_corporativo(
        titulo_hoja="Clientes",
        titulo_reporte="HOMEX — Listado de Clientes",
        subtitulo_filtros=subtitulo,
        columnas=columnas,
        filas=_filas(),
        anchos=[9, 14, 26, 24, 15, 32, 28, 12],
        integer_cols={1},
    )
    filename = construir_nombre_exportacion(
        "clientes",
        [activo_lbl, tipo_lbl, search_raw, desde_raw, "a", hasta_raw],
    )
    return respuesta_excel(contenido=contenido, filename=filename)


def exportar_recibos_excel(queryset, query_params):
    desde, hasta = validar_rango_fechas(
        query_params.get("fecha_desde"),
        query_params.get("fecha_hasta"),
        obligatorio=True,
    )
    assert desde is not None and hasta is not None
    queryset = queryset.filter(fecha__range=(desde, hasta))
    estado_raw = (query_params.get("estado") or "").strip()
    estado_lbl = (
        "Emitido"
        if estado_raw.upper() == "EMITIDO"
        else ("Anulado" if estado_raw.upper() == "ANULADO" else estado_raw)
    )
    tipo_pago_lbl = _nombre_valor_catalogo(query_params.get("tipo_pago"), grupo="TIPO_PAGO")
    search_raw = (query_params.get("search") or "").strip()
    desde_raw = desde.isoformat()
    hasta_raw = hasta.isoformat()
    subtitulo = _subtitulo_filtros_valores(
        [
            ("Búsqueda", search_raw),
            ("Estado", estado_lbl),
            ("Tipo de pago", tipo_pago_lbl),
            ("Desde", desde_raw),
            ("Hasta", hasta_raw),
        ]
    )
    columnas = [
        "Recibo #",
        "Pedido #",
        "Fecha",
        "Pagador",
        "Tipo de pago",
        "Estado",
        "Moneda",
        "Pago actual",
        "A cuenta",
        "Saldo",
        "Total pedido",
        "Banco",
        "N.º cheque",
        "Vendedor",
    ]

    def _filas():
        for rec in queryset.select_related(
            "pedido__proforma__moneda",
            "pedido__proforma__vendedor",
            "tipo_pago",
        ).iterator(chunk_size=500):
            pf = rec.pedido.proforma
            yield [
                rec.numero,
                rec.pedido_id,
                rec.fecha,
                rec.nombre_completo,
                rec.tipo_pago.nombre,
                rec.estado,
                pf.moneda.codigo,
                rec.pago_actual,
                rec.a_cuenta,
                rec.saldo,
                rec.total,
                rec.banco or "",
                rec.numero_cheque or "",
                _nombre_usuario(pf.vendedor),
            ]

    contenido = generar_excel_corporativo(
        titulo_hoja="Recibos",
        titulo_reporte="HOMEX — Listado de Recibos",
        subtitulo_filtros=subtitulo,
        columnas=columnas,
        filas=_filas(),
        anchos=[11, 11, 13, 26, 18, 12, 10, 14, 14, 14, 14, 18, 15, 22],
        integer_cols={1, 2},
        currency_cols={8, 9, 10, 11},
        date_cols={3},
    )
    filename = construir_nombre_exportacion(
        "recibos",
        [estado_lbl, tipo_pago_lbl, search_raw, desde_raw, "a", hasta_raw],
    )
    return respuesta_excel(contenido=contenido, filename=filename)
