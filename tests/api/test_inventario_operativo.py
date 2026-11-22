import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.db import close_old_connections
from rest_framework.test import APIClient

from apps.catalogo.models import Producto, ProductoPiso
from apps.movimientos_stock.models import MovimientoStock
from apps.proformas.models import DetalleProforma, Proforma
from tests.factories import cargar_stock, cliente_persona, silla, valor, vendedor


def _admin(django_user_model, username="inv-admin"):
    return django_user_model.objects.create_user(
        username=username,
        is_staff=True,
    )


def _jefe_taller(django_user_model, username="inv-taller"):
    user = django_user_model.objects.create_user(username=username)
    grupo, _ = Group.objects.get_or_create(name="JEFE_TALLER")
    user.groups.add(grupo)
    return user


def _silla_con_stock(actor, *, sku, stock=0):
    prod = silla(actor, sku=sku, stock=0)
    if Decimal(str(stock)) > 0:
        cargar_stock(prod, actor, Decimal(str(stock)))
        prod.refresh_from_db()
    return prod


def _piso_m2(actor, *, sku="P-M2-1", stock="0"):
    producto = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "PISO_FLOTANTE"),
        sku=sku,
        nombre=f"Piso {sku}",
        precio_lista=Decimal("120.00"),
        unidad_stock=valor("UNIDAD_MEDIDA", "M2"),
        created_by=actor,
        updated_by=actor,
    )
    ProductoPiso.objects.create(
        producto=producto,
        espesor_mm=Decimal("8.00"),
        m2_por_caja=Decimal("2.4000"),
        created_by=actor,
        updated_by=actor,
    )
    if Decimal(str(stock)) > 0:
        cargar_stock(producto, actor, Decimal(str(stock)))
        producto.refresh_from_db()
    return producto


@pytest.mark.django_db(transaction=True)
def test_p2_ajuste_entrada_salida_permisos_y_validaciones(django_user_model):
    admin = _admin(django_user_model)
    tienda = vendedor(django_user_model.objects.create_user(username="inv-tienda"))
    taller = _jefe_taller(django_user_model)
    prod = _silla_con_stock(admin, sku="INV-P2-1", stock=10)

    # Permisos: Encargado de tienda y Jefe de taller no pueden registrar ajustes
    for usuario in (tienda, taller):
        cli = APIClient()
        cli.force_authenticate(usuario)
        resp = cli.post(
            "/api/v1/movimientos-stock/ajustes/",
            {
                "producto": prod.id,
                "tipo_operacion": "ENTRADA",
                "cantidad": "5",
                "motivo": "REPOSICION",
            },
            format="json",
        )
        assert resp.status_code == 403

    cli_admin = APIClient()
    cli_admin.force_authenticate(admin)

    # Falta Idempotency-Key -> 400
    resp_sin_clave = cli_admin.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "ENTRADA",
            "cantidad": "1",
            "motivo": "REPOSICION",
        },
        format="json",
    )
    assert resp_sin_clave.status_code == 400

    # Corrección excepcional exige observación justificativa
    resp_sin_obs = cli_admin.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "ENTRADA",
            "cantidad": "2",
            "motivo": "CORRECCION_EXCEPCIONAL",
            "observaciones": "   ",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert resp_sin_obs.status_code == 400
    assert "observaciones" in resp_sin_obs.data

    # Unidad entera PIEZA rechaza decimales
    resp_dec = cli_admin.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "ENTRADA",
            "cantidad": "1.5",
            "motivo": "REPOSICION",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert resp_dec.status_code == 400
    assert "cantidad" in resp_dec.data

    # Entrada válida actualiza stock vía trigger PostgreSQL
    clave = str(uuid.uuid4())
    resp_ok = cli_admin.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "ENTRADA",
            "cantidad": "5",
            "motivo": "REPOSICION",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=clave,
    )
    assert resp_ok.status_code == 201
    assert Decimal(resp_ok.data["cantidad"]) == Decimal("5")
    assert resp_ok.data["motivo"] == "REPOSICION"
    assert resp_ok.data["motivo_label"] == "Reposición"
    prod.refresh_from_db()
    assert prod.stock == Decimal("15")

    # Idempotencia por Idempotency-Key evita duplicados en reintento / doble clic
    resp_replay = cli_admin.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "ENTRADA",
            "cantidad": "5",
            "motivo": "REPOSICION",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=clave,
    )
    assert resp_replay.status_code == 200
    assert resp_replay.data["id"] == resp_ok.data["id"]
    prod.refresh_from_db()
    assert prod.stock == Decimal("15")

    # Reutilizar la misma clave con SALIDA y cantidad negativa (-5) -> HTTP 400 (no 200)
    resp_neg_reuso = cli_admin.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "SALIDA",
            "cantidad": "-5",
            "motivo": "MERMA",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=clave,
    )
    assert resp_neg_reuso.status_code == 400
    assert "cantidad" in resp_neg_reuso.data

    # Cantidad cero -> HTTP 400
    resp_cero = cli_admin.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "ENTRADA",
            "cantidad": "0",
            "motivo": "REPOSICION",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert resp_cero.status_code == 400
    assert "cantidad" in resp_cero.data

    # Motivo incompatible con tipo_operacion -> HTTP 400 incluso con clave existente
    resp_motivo_incomp = cli_admin.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "ENTRADA",
            "cantidad": "5",
            "motivo": "MERMA",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=clave,
    )
    assert resp_motivo_incomp.status_code == 400
    assert "motivo" in resp_motivo_incomp.data

    # Reutilizar la misma clave con cambio de dirección (SALIDA 5) -> HTTP 409
    resp_conflicto_dir = cli_admin.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "SALIDA",
            "cantidad": "5",
            "motivo": "MERMA",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=clave,
    )
    assert resp_conflicto_dir.status_code == 409

    # Reutilizar la misma clave con datos diferentes o distinto usuario -> HTTP 409
    resp_conflicto_qty = cli_admin.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "ENTRADA",
            "cantidad": "6",
            "motivo": "REPOSICION",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=clave,
    )
    assert resp_conflicto_qty.status_code == 409

    otro_admin = _admin(django_user_model, username="inv-admin-2")
    cli_otro = APIClient()
    cli_otro.force_authenticate(otro_admin)
    resp_conflicto_user = cli_otro.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "ENTRADA",
            "cantidad": "5",
            "motivo": "REPOSICION",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=clave,
    )
    assert resp_conflicto_user.status_code == 409

    # Salida no puede generar stock negativo
    resp_neg = cli_admin.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "SALIDA",
            "cantidad": "20",
            "motivo": "MERMA",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert resp_neg.status_code == 400
    assert "cantidad" in resp_neg.data

    # Salida válida
    resp_salida = cli_admin.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "SALIDA",
            "cantidad": "4",
            "motivo": "DANO",
            "observaciones": "Golpe en almacén",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert resp_salida.status_code == 201
    assert Decimal(resp_salida.data["cantidad"]) == Decimal("-4")
    prod.refresh_from_db()
    assert prod.stock == Decimal("11")

    # El endpoint raíz sigue siendo read-only (no permite crear VENTA/REVERSA_VENTA/CARGA_INICIAL)
    assert cli_admin.post("/api/v1/movimientos-stock/", {}, format="json").status_code == 405


@pytest.mark.django_db(transaction=True)
def test_p2_ajuste_decimal_m2_y_concurrencia(django_user_model):
    admin = _admin(django_user_model, username="inv-admin-m2")
    piso = _piso_m2(admin, sku="INV-M2-1", stock="10.0000")
    cli = APIClient()
    cli.force_authenticate(admin)

    resp = cli.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": piso.id,
            "tipo_operacion": "SALIDA",
            "cantidad": "2.1234",
            "motivo": "USO_INTERNO",
            "observaciones": "Muestra showroom",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert resp.status_code == 201
    piso.refresh_from_db()
    assert piso.stock == Decimal("7.8766")

    # Stock mínimo M2 con 4 decimales
    r_min = cli.patch(
        f"/api/v1/catalogo/productos/{piso.id}/stock-minimo/",
        {"stock_minimo": "1.2345"},
        format="json",
    )
    assert r_min.status_code == 200
    assert Decimal(r_min.data["stock_minimo"]) == Decimal("1.2345")

    # Concurrencia: dos solicitudes con la misma clave idempotente -> 200 + 201, sin duplicar
    clave_conc = str(uuid.uuid4())

    def _intentar_idempotente(_idx):
        close_old_connections()
        c = APIClient()
        c.force_authenticate(admin)
        return c.post(
            "/api/v1/movimientos-stock/ajustes/",
            {
                "producto": piso.id,
                "tipo_operacion": "SALIDA",
                "cantidad": "1.0000",
                "motivo": "MERMA",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=clave_conc,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codigos_idem = sorted(pool.map(_intentar_idempotente, [1, 2]))

    assert codigos_idem == [200, 201]
    piso.refresh_from_db()
    assert piso.stock == Decimal("6.8766")

    # Concurrencia: dos salidas de 5.0000 sobre stock 6.8766 -> solo una debe pasar
    def _intentar_salida(_idx):
        close_old_connections()
        c = APIClient()
        c.force_authenticate(admin)
        return c.post(
            "/api/v1/movimientos-stock/ajustes/",
            {
                "producto": piso.id,
                "tipo_operacion": "SALIDA",
                "cantidad": "5.0000",
                "motivo": "REGULARIZACION_NEGATIVA",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codigos = sorted(pool.map(_intentar_salida, [1, 2]))

    assert codigos == [201, 400]
    piso.refresh_from_db()
    assert piso.stock == Decimal("1.8766")


@pytest.mark.django_db(transaction=True)
def test_p4_desglose_demanda_pendiente_y_aislamiento(django_user_model):
    admin = _admin(django_user_model, username="inv-p4-admin")
    vendedor_a = vendedor(django_user_model.objects.create_user(username="inv-p4-a"))
    vendedor_b = vendedor(django_user_model.objects.create_user(username="inv-p4-b"))
    prod = _silla_con_stock(admin, sku="INV-P4-1", stock=10)
    cli_a = cliente_persona(vendedor_a, sufijo="p4a")
    cli_b = cliente_persona(vendedor_b, sufijo="p4b")

    prof_a = Proforma.objects.create(
        numero=91001,
        cliente=cli_a,
        vendedor=vendedor_a,
        estado=valor("ESTADO_PROFORMA", "BORRADOR"),
        fecha="2026-11-20",
        moneda=valor("MONEDA", "BOB"),
    )
    DetalleProforma.objects.create(
        proforma=prof_a,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto=prod,
        nombre=prod.nombre,
        cantidad=Decimal("3"),
        unidad=prod.unidad_stock,
        precio_unitario=Decimal("50.00"),
        total=Decimal("150.00"),
    )
    prof_a.estado = valor("ESTADO_PROFORMA", "EN_REVISION")
    prof_a.save(update_fields=["estado"])

    prof_b = Proforma.objects.create(
        numero=91002,
        cliente=cli_b,
        vendedor=vendedor_b,
        estado=valor("ESTADO_PROFORMA", "BORRADOR"),
        fecha="2026-11-20",
        moneda=valor("MONEDA", "BOB"),
    )
    DetalleProforma.objects.create(
        proforma=prof_b,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto=prod,
        nombre=prod.nombre,
        cantidad=Decimal("4"),
        unidad=prod.unidad_stock,
        precio_unitario=Decimal("50.00"),
        total=Decimal("200.00"),
    )
    prof_b.estado = valor("ESTADO_PROFORMA", "ENVIADA")
    prof_b.save(update_fields=["estado"])

    # Admin ve ambas proformas
    c_admin = APIClient()
    c_admin.force_authenticate(admin)
    r_admin = c_admin.get(f"/api/v1/catalogo/productos/{prod.id}/demanda-pendiente/")
    assert r_admin.status_code == 200
    assert Decimal(r_admin.data["demanda_pendiente_total"]) == Decimal("7")
    assert Decimal(r_admin.data["cantidad_restringida"]) == Decimal("0")
    assert {p["numero"] for p in r_admin.data["proformas"]} == {91001, 91002}

    # Vendedor A solo ve la suya y no se expone la proforma de B
    c_a = APIClient()
    c_a.force_authenticate(vendedor_a)
    r_a = c_a.get(f"/api/v1/catalogo/productos/{prod.id}/demanda-pendiente/")
    assert r_a.status_code == 200
    assert Decimal(r_a.data["demanda_pendiente_total"]) == Decimal("7")
    assert Decimal(r_a.data["cantidad_restringida"]) == Decimal("4")
    assert [p["numero"] for p in r_a.data["proformas"]] == [91001]


@pytest.mark.django_db(transaction=True)
def test_p5_stock_minimo_permisos_unidad_y_estados(django_user_model):
    admin = _admin(django_user_model, username="inv-p5-admin")
    tienda = vendedor(django_user_model.objects.create_user(username="inv-p5-tienda"))
    prod = _silla_con_stock(admin, sku="INV-P5-1", stock=5)

    c_tienda = APIClient()
    c_tienda.force_authenticate(tienda)
    assert (
        c_tienda.get(f"/api/v1/catalogo/productos/{prod.id}/").data["estado_stock"] == "SIN_MINIMO"
    )
    assert (
        c_tienda.patch(
            f"/api/v1/catalogo/productos/{prod.id}/stock-minimo/",
            {"stock_minimo": "3"},
            format="json",
        ).status_code
        == 403
    )

    c_admin = APIClient()
    c_admin.force_authenticate(admin)
    # PIEZA rechaza decimal
    assert (
        c_admin.patch(
            f"/api/v1/catalogo/productos/{prod.id}/stock-minimo/",
            {"stock_minimo": "2.5"},
            format="json",
        ).status_code
        == 400
    )

    # Configurar mínimo = 5 -> stock 5 <= 5 -> STOCK_BAJO
    r_low = c_admin.patch(
        f"/api/v1/catalogo/productos/{prod.id}/stock-minimo/",
        {"stock_minimo": "5"},
        format="json",
    )
    assert r_low.status_code == 200
    assert r_low.data["estado_stock"] == "STOCK_BAJO"

    # Configurar mínimo = 4 -> stock 5 > 4 -> NORMAL
    r_norm = c_admin.patch(
        f"/api/v1/catalogo/productos/{prod.id}/stock-minimo/",
        {"stock_minimo": "4"},
        format="json",
    )
    assert r_norm.status_code == 200
    assert r_norm.data["estado_stock"] == "NORMAL"

    # Producto en cero -> SIN_EXISTENCIAS
    prod_cero = _silla_con_stock(admin, sku="INV-P5-0", stock=0)
    assert c_admin.get(f"/api/v1/catalogo/productos/{prod_cero.id}/").data["estado_stock"] == (
        "SIN_EXISTENCIAS"
    )


@pytest.mark.django_db(transaction=True)
def test_p6_reporte_saldos_historicos_y_exportacion_csv(django_user_model):
    admin = _admin(django_user_model, username="inv-p6-admin")
    prod = _silla_con_stock(admin, sku="INV-P6-1", stock=10)
    cli = APIClient()
    cli.force_authenticate(admin)

    cli.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "SALIDA",
            "cantidad": "3",
            "motivo": "MERMA",
            "observaciones": "  =SUM(A1:A2)",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    cli.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "ENTRADA",
            "cantidad": "2",
            "motivo": "REPOSICION",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    # Sin filtro de producto no mezcla unidades ni inventa saldos
    r_global = cli.get("/api/v1/movimientos-stock/reporte/")
    assert r_global.status_code == 200
    assert r_global.data["saldo_reconstruible"] is False
    assert r_global.data["resumen"] is None

    # Con producto específico calcula saldos históricos exactos
    r_prod = cli.get("/api/v1/movimientos-stock/reporte/", {"producto": prod.id})
    assert r_prod.status_code == 200
    assert r_prod.data["saldo_reconstruible"] is True
    assert Decimal(r_prod.data["resumen"]["total_entradas"]) == Decimal("12")
    assert Decimal(r_prod.data["resumen"]["total_salidas"]) == Decimal("3")
    assert Decimal(r_prod.data["resumen"]["variacion_neta"]) == Decimal("9")
    assert Decimal(r_prod.data["resumen"]["stock_actual"]) == Decimal("9")
    assert len(r_prod.data["results"]) == 3
    # Orden descendente: el último movimiento (+2) dejó saldo 9
    assert Decimal(r_prod.data["results"][0]["saldo_posterior"]) == Decimal("9")
    assert Decimal(r_prod.data["results"][0]["saldo_anterior"]) == Decimal("7")

    # Exportación CSV compatible con Excel (BOM UTF-8) y respeta filtros
    r_csv = cli.get(
        "/api/v1/movimientos-stock/exportar-csv/",
        {"producto": prod.id, "direccion": "SALIDA"},
    )
    assert r_csv.status_code == 200
    assert r_csv["Content-Type"].startswith("text/csv")
    contenido = r_csv.content.decode("utf-8-sig")
    lineas = [linea for linea in contenido.strip().splitlines() if linea]
    assert len(lineas) == 2  # Header + 1 salida (-3)
    assert "INV-P6-1" in lineas[1]
    assert "-3.0000" in lineas[1]
    assert "'=SUM(A1:A2)" in lineas[1]

    from apps.movimientos_stock.services import _sanitizar_celda_csv

    for peligroso in ("=SUM(A1)", "  =SUM(A1)", " +1", " -1", "@cmd", "\tfoo", "\nbar", "\rbaz"):
        assert _sanitizar_celda_csv(peligroso).startswith("'")

    # Período sin movimientos y filtro por dirección mantienen saldos temporales reales
    from django.utils import timezone

    hoy = timezone.localdate()
    r_vacio = cli.get(
        "/api/v1/movimientos-stock/reporte/",
        {"producto": prod.id, "fecha_desde": "2099-01-01", "fecha_hasta": "2099-01-31"},
    )
    assert r_vacio.status_code == 200
    assert Decimal(r_vacio.data["resumen"]["saldo_inicial_periodo"]) == Decimal("9")
    assert Decimal(r_vacio.data["resumen"]["saldo_final_periodo"]) == Decimal("9")
    assert r_vacio.data["resumen"]["cantidad_movimientos"] == 0

    # Filtro combinado por dirección=ENTRADA + motivo=REPOSICION mantiene saldos del período
    r_filtrado = cli.get(
        "/api/v1/movimientos-stock/reporte/",
        {
            "producto": prod.id,
            "direccion": "ENTRADA",
            "motivo": "REPOSICION",
            "fecha_desde": str(hoy),
        },
    )
    assert r_filtrado.status_code == 200
    assert Decimal(r_filtrado.data["resumen"]["total_entradas"]) == Decimal("2")
    assert Decimal(r_filtrado.data["resumen"]["total_salidas"]) == Decimal("0")
    assert Decimal(r_filtrado.data["resumen"]["saldo_inicial_periodo"]) == Decimal("0")
    assert Decimal(r_filtrado.data["resumen"]["saldo_final_periodo"]) == Decimal("9")

    # Verificar que no se puede mutar un movimiento existente (inmutabilidad DB)
    mov = MovimientoStock.objects.filter(producto=prod).first()
    with pytest.raises(Exception):
        MovimientoStock.objects.filter(pk=mov.pk).update(cantidad=Decimal("99"))


@pytest.mark.django_db(transaction=True)
def test_buscador_movimientos_sku_nombre_responsable_y_pedido_exacto(django_user_model):
    from apps.pedidos.services import cancelar_pedido
    from tests.integration.test_f074_cobros import crear_pedido_confirmado

    admin = django_user_model.objects.create_user(
        username="ana.perez",
        first_name="Ana",
        last_name="Pérez",
        is_staff=True,
    )
    prod = _silla_con_stock(admin, sku="SKU-BUSCA-1", stock=10)
    cli = APIClient()
    cli.force_authenticate(admin)

    # Ajuste con observación única que NO debe aparecer en search
    cli.post(
        "/api/v1/movimientos-stock/ajustes/",
        {
            "producto": prod.id,
            "tipo_operacion": "ENTRADA",
            "cantidad": "1",
            "motivo": "REPOSICION",
            "observaciones": "PALABRA_SECRETA_OBS",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    # Pedido confirmado y cancelado (genera VENTA y REVERSA_VENTA)
    pedido_1, _ = crear_pedido_confirmado(admin, sku="SKU-PED-A", cantidad=2)
    cancelar_pedido(pedido_id=pedido_1.id, actor=admin)

    # Búsqueda por #pedido encuentra VENTA y REVERSA_VENTA del pedido exacto
    r_ped = cli.get("/api/v1/movimientos-stock/", {"search": f"#{pedido_1.id}"})
    assert r_ped.status_code == 200
    tipos = {item["tipo_movimiento_info"]["codigo"] for item in r_ped.data["results"]}
    assert tipos == {"VENTA", "REVERSA_VENTA"}

    # Búsqueda por #pedido inexistente no hace coincidencia parcial
    r_no_ped = cli.get("/api/v1/movimientos-stock/", {"search": f"#{pedido_1.id}99"})
    assert r_no_ped.status_code == 200
    assert r_no_ped.data["count"] == 0

    # Búsqueda por nombre, apellido, nombre completo y username del responsable
    for q in ("Ana", "Pérez", "Ana Pérez", "ana.perez"):
        r_resp = cli.get("/api/v1/movimientos-stock/", {"search": q})
        assert r_resp.status_code == 200
        assert r_resp.data["count"] >= 1

    # Búsqueda por observaciones NO retorna resultados
    r_obs = cli.get("/api/v1/movimientos-stock/", {"search": "PALABRA_SECRETA_OBS"})
    assert r_obs.status_code == 200
    assert r_obs.data["count"] == 0
