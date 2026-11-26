"""Exportadores Excel (.xlsx) reutilizables para todas las bandejas HOMEX."""

from __future__ import annotations

from apps.core.excel import generar_excel_corporativo, respuesta_excel
from apps.core.serializers import resumen_usuario
from apps.proformas.vigencia import fecha_limite


def _subtitulo_filtros(query_params, etiquetas: dict[str, str]) -> str:
    partes = []
    for clave, etiqueta in etiquetas.items():
        valor = (query_params.get(clave) or "").strip()
        if valor:
            partes.append(f"{etiqueta}: {valor}")
    return "   |   ".join(partes) if partes else "Filtros: Ninguno (listado completo)"


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
    subtitulo = _subtitulo_filtros(
        query_params,
        {
            "search": "Búsqueda",
            "estado": "Estado",
            "moneda": "Moneda",
            "fecha_desde": "Desde",
            "fecha_hasta": "Hasta",
            "orden": "Orden",
        },
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
    return respuesta_excel(contenido=contenido, filename="proformas.xlsx")


def exportar_productos_excel(queryset, query_params):
    subtitulo = _subtitulo_filtros(
        query_params,
        {
            "search": "Búsqueda",
            "categoria": "Categoría",
            "familia": "Familia",
            "activo": "Activo",
            "modalidad": "Modalidad",
        },
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
    return respuesta_excel(contenido=contenido, filename="productos.xlsx")


def exportar_pedidos_excel(queryset, query_params):
    subtitulo = _subtitulo_filtros(
        query_params,
        {
            "search": "Búsqueda",
            "estado": "Estado",
            "fecha_desde": "Desde",
            "fecha_hasta": "Hasta",
        },
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
    return respuesta_excel(contenido=contenido, filename="pedidos.xlsx")


def exportar_ordenes_trabajo_excel(queryset, query_params):
    """Exporta órdenes de trabajo sin exponer información financiera."""
    subtitulo = _subtitulo_filtros(
        query_params,
        {
            "search": "Búsqueda",
            "estado": "Estado",
            "fecha_desde": "Desde",
            "fecha_hasta": "Hasta",
        },
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
    return respuesta_excel(contenido=contenido, filename="ordenes-trabajo.xlsx")


def exportar_notas_entrega_excel(queryset, query_params):
    subtitulo = _subtitulo_filtros(
        query_params,
        {
            "search": "Búsqueda",
            "fecha_desde": "Desde",
            "fecha_hasta": "Hasta",
        },
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
    return respuesta_excel(contenido=contenido, filename="notas-entrega.xlsx")


def exportar_clientes_excel(queryset, query_params):
    subtitulo = _subtitulo_filtros(
        query_params,
        {
            "search": "Búsqueda",
            "tipo_cliente": "Tipo",
            "activo": "Activo",
        },
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
    return respuesta_excel(contenido=contenido, filename="clientes.xlsx")


def exportar_recibos_excel(queryset, query_params):
    subtitulo = _subtitulo_filtros(
        query_params,
        {
            "search": "Búsqueda",
            "estado": "Estado",
            "tipo_pago": "Tipo de pago",
            "fecha_desde": "Desde",
            "fecha_hasta": "Hasta",
        },
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
    return respuesta_excel(contenido=contenido, filename="recibos.xlsx")
