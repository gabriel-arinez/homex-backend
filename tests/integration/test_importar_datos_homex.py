import hashlib
import io
import json
import stat
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.accounts.models import User
from apps.catalogo.models import Producto
from apps.clientes.models import Cliente
from apps.movimientos_stock.models import MovimientoStock
from apps.notas_entrega.models import NotaEntrega
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.models import Pedido
from apps.proformas.models import Proforma
from apps.recibos.models import Recibo


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _construir_zip_escenario(
    tmp_path: Path,
    *,
    nombre: str = "escenario_test.zip",
    corromper_sha: bool = False,
    agregar_zip_slip: bool = False,
    agregar_symlink: bool = False,
    agregar_entrada_duplicada: bool = False,
    agregar_colision_normalizada: bool = False,
    omitir_obligatorio_en_manifiesto: bool = False,
    cliente_inexistente: bool = False,
    evento_invalido_al_final: bool = False,
    modificar_precio_en_reintento: bool = False,
    oraculo_conciliacion_invalido: bool = False,
) -> Path:
    precio_silla = "950.00" if modificar_precio_en_reintento else "900.00"
    total_pf1 = "1900.00" if modificar_precio_en_reintento else "1800.00"
    recibo_pago = "950.00" if modificar_precio_en_reintento else "900.00"

    catalogo = [
        {
            "sku": "EVAL-SILLA-01",
            "sku_fuente": "S01",
            "nombre": "Silla Evaluacion [EVAL]",
            "categoria": "SILLA",
            "unidad_stock": "PIEZA",
            "modalidad_abastecimiento": "CON_STOCK",
            "precio_lista": precio_silla,
            "stock_inicial": "10",
            "stock_minimo": None,
            "ficha": {
                "marca": "EVAL_NO_ESPECIFICADA",
                "modelo": "S01",
                "color_primario": "NEGRO",
                "especificaciones": {"origen": "EVAL"},
            },
        },
        {
            "sku": "EVAL-PISO-BP",
            "sku_fuente": "PBP",
            "nombre": "Piso Bajo Pedido [EVAL]",
            "categoria": "PISO_FLOTANTE",
            "unidad_stock": "M2",
            "modalidad_abastecimiento": "BAJO_PEDIDO",
            "precio_lista": "150.00",
            "stock_inicial": "0",
            "stock_minimo": None,
            "ficha": {
                "marca": "GANESHA",
                "modelo": "BP-01",
                "m2_por_caja": "2.5000",
            },
        },
    ]

    clientes = [
        {
            "id": "EVAL-CLI-01",
            "tipo_cliente": "PERSONA",
            "empresa": None,
            "nombres": "Juan",
            "apellidos": "EVAL-CLI-01",
            "celular": None,
            "direccion": None,
            "created_by": "alvaro.huallpa",
            "naturaleza": "SIMULADO_NO_RESULTADO_MEDIDO",
        },
        {
            "id": "EVAL-CLI-02",
            "tipo_cliente": "EMPRESA",
            "empresa": "Empresa EVAL-CLI-02",
            "nombres": "Contacto",
            "apellidos": "EVAL-CLI-02",
            "celular": None,
            "direccion": None,
            "created_by": "rodrigo.ramos",
            "naturaleza": "SIMULADO_NO_RESULTADO_MEDIDO",
        },
    ]

    plantillas = []

    proformas = [
        {
            "id": "EVAL-PF-01",
            "cliente_id": "CLI-INEXISTENTE" if cliente_inexistente else "EVAL-CLI-01",
            "vendedor": "alvaro.huallpa",
            "fecha": "2026-10-01",
            "mes_cohorte": "2026-10",
            "estado_objetivo": "APROBADA",
            "formalizada": True,
            "moneda": "BOB",
            "validez_oferta": 7,
            "plazo_entrega": "5 días",
            "porcentaje_adelanto": "50",
            "tipo_comercial": "MIXTO",
            "titulo": "[SIMULACIÓN] EVAL-PF-01",
            "observaciones": "Prueba integral",
            "lineas": [
                {
                    "tipo_item": "SILLA",
                    "sku": "EVAL-SILLA-01",
                    "nombre": "Silla Evaluacion [EVAL]",
                    "cantidad": "2",
                    "unidad": "PIEZA",
                    "modo_calculo": "PRECIO_UNITARIO",
                    "precio_unitario": precio_silla,
                    "descuento": "0.00",
                    "total": total_pf1,
                },
                {
                    "tipo_item": "MUEBLE_MEDIDA",
                    "sku": None,
                    "nombre": "ESCRITORIO RECTO",
                    "descripcion": "Escritorio de prueba",
                    "cantidad": "1",
                    "unidad": "PIEZA",
                    "modo_calculo": "PRECIO_UNITARIO",
                    "precio_unitario": "1000.00",
                    "descuento": "0.00",
                    "total": "1000.00",
                    "especificacion": {
                        "tipo_mueble": "ESCRITORIO",
                        "datos_tecnicos": {"descripcion_original": "Escritorio de prueba"},
                    },
                },
            ],
            "subtotal": "2900.00" if modificar_precio_en_reintento else "2800.00",
            "descuento_total": "0.00",
            "total": "2900.00" if modificar_precio_en_reintento else "2800.00",
            "naturaleza": "SIMULADO_NO_RESULTADO_MEDIDO",
        },
        {
            "id": "EVAL-PF-02",
            "cliente_id": "EVAL-CLI-02",
            "vendedor": "rodrigo.ramos",
            "fecha": "2026-10-02",
            "mes_cohorte": "2026-10",
            "estado_objetivo": "APROBADA",
            "formalizada": True,
            "moneda": "BOB",
            "validez_oferta": 7,
            "plazo_entrega": "5 días",
            "porcentaje_adelanto": "50",
            "tipo_comercial": "CATALOGO",
            "titulo": "[SIMULACIÓN] EVAL-PF-02",
            "observaciones": "Cancelación",
            "lineas": [
                {
                    "tipo_item": "SILLA",
                    "sku": "EVAL-SILLA-01",
                    "nombre": "Silla Evaluacion [EVAL]",
                    "cantidad": "3",
                    "unidad": "PIEZA",
                    "modo_calculo": "PRECIO_UNITARIO",
                    "precio_unitario": precio_silla,
                    "descuento": "0.00",
                    "total": "2850.00" if modificar_precio_en_reintento else "2700.00",
                }
            ],
            "subtotal": "2850.00" if modificar_precio_en_reintento else "2700.00",
            "descuento_total": "0.00",
            "total": "2850.00" if modificar_precio_en_reintento else "2700.00",
            "naturaleza": "SIMULADO_NO_RESULTADO_MEDIDO",
        },
        {
            "id": "EVAL-PF-03",
            "cliente_id": "EVAL-CLI-01",
            "vendedor": "alvaro.huallpa",
            "fecha": "2026-11-26",
            "mes_cohorte": "2026-11",
            "estado_objetivo": "BORRADOR",
            "formalizada": False,
            "moneda": "BOB",
            "validez_oferta": 7,
            "plazo_entrega": "5 días",
            "porcentaje_adelanto": "50",
            "tipo_comercial": "PISO",
            "titulo": "[SIMULACIÓN] EVAL-PF-03",
            "observaciones": "Evento futuro",
            "lineas": [
                {
                    "tipo_item": "PISO_FLOTANTE",
                    "sku": "EVAL-PISO-BP",
                    "nombre": "Piso Bajo Pedido [EVAL]",
                    "cantidad": "4.00",
                    "unidad": "M2",
                    "modo_calculo": "PRECIO_UNITARIO",
                    "precio_unitario": "150.00",
                    "descuento": "0.00",
                    "total": "600.00",
                }
            ],
            "subtotal": "600.00",
            "descuento_total": "0.00",
            "total": "600.00",
            "naturaleza": "SIMULADO_NO_RESULTADO_MEDIDO",
        },
    ]

    eventos = [
        {
            "id": "EV-01",
            "proforma_id": "EVAL-PF-01",
            "tipo": "CREAR_BORRADOR",
            "fecha": "2026-10-01",
            "actor": "alvaro.huallpa",
            "posterior_a_fecha_preparacion": False,
            "orden_ejecucion": 1,
        },
        {
            "id": "EV-02",
            "proforma_id": "EVAL-PF-01",
            "tipo": "ENVIAR_PROFORMA",
            "fecha": "2026-10-01",
            "actor": "alvaro.huallpa",
            "posterior_a_fecha_preparacion": False,
            "orden_ejecucion": 2,
        },
        {
            "id": "EV-03",
            "proforma_id": "EVAL-PF-01",
            "tipo": "APROBAR_PROFORMA",
            "fecha": "2026-10-02",
            "actor": "alvaro.huallpa",
            "pedido_id": "EVAL-PED-01",
            "posterior_a_fecha_preparacion": False,
            "orden_ejecucion": 3,
        },
        {
            "id": "EV-04",
            "proforma_id": "EVAL-PF-01",
            "tipo": "EMITIR_RECIBO",
            "fecha": "2026-10-02",
            "actor": "alvaro.huallpa",
            "pedido_id": "EVAL-PED-01",
            "recibo_id": "EVAL-REC-01",
            "posterior_a_fecha_preparacion": False,
            "orden_ejecucion": 4,
        },
        {
            "id": "EV-05",
            "proforma_id": "EVAL-PF-01",
            "tipo": "EN_PRODUCCION",
            "fecha": "2026-10-03",
            "actor": "alvaro.huallpa",
            "pedido_id": "EVAL-PED-01",
            "posterior_a_fecha_preparacion": False,
            "orden_ejecucion": 5,
        },
        {
            "id": "EV-06",
            "proforma_id": "EVAL-PF-01",
            "tipo": "LISTO_ENTREGA",
            "fecha": "2026-10-05",
            "actor": "antonio.flores",
            "pedido_id": "EVAL-PED-01",
            "posterior_a_fecha_preparacion": False,
            "orden_ejecucion": 6,
        },
        {
            "id": "EV-07",
            "proforma_id": "EVAL-PF-01",
            "tipo": "ENTREGADO",
            "fecha": "2026-10-06",
            "actor": "alvaro.huallpa",
            "pedido_id": "EVAL-PED-01",
            "posterior_a_fecha_preparacion": False,
            "orden_ejecucion": 7,
        },
        {
            "id": "EV-08",
            "proforma_id": "EVAL-PF-02",
            "tipo": "CREAR_BORRADOR",
            "fecha": "2026-10-02",
            "actor": "rodrigo.ramos",
            "posterior_a_fecha_preparacion": False,
            "orden_ejecucion": 8,
        },
        {
            "id": "EV-09",
            "proforma_id": "EVAL-PF-02",
            "tipo": "ENVIAR_PROFORMA",
            "fecha": "2026-10-02",
            "actor": "rodrigo.ramos",
            "posterior_a_fecha_preparacion": False,
            "orden_ejecucion": 9,
        },
        {
            "id": "EV-10",
            "proforma_id": "EVAL-PF-02",
            "tipo": "APROBAR_PROFORMA",
            "fecha": "2026-10-03",
            "actor": "rodrigo.ramos",
            "pedido_id": "EVAL-PED-02",
            "posterior_a_fecha_preparacion": False,
            "orden_ejecucion": 10,
        },
        {
            "id": "EV-11",
            "proforma_id": "EVAL-PF-02",
            "tipo": "CANCELAR_PEDIDO",
            "fecha": "2026-10-04",
            "actor": "rodrigo.ramos",
            "pedido_id": "EVAL-PED-02",
            "posterior_a_fecha_preparacion": False,
            "orden_ejecucion": 11,
        },
        {
            "id": "EV-12",
            "proforma_id": "EVAL-PF-03",
            "tipo": "CREAR_BORRADOR",
            "fecha": "2026-11-26",
            "actor": "alvaro.huallpa",
            "posterior_a_fecha_preparacion": True,
            "orden_ejecucion": 12,
        },
    ]
    if evento_invalido_al_final:
        # Intentar enviar proforma ya entregada/aprobada para provocar rollback atómico
        eventos.append(
            {
                "id": "EV-99",
                "proforma_id": "EVAL-PF-01",
                "tipo": "ANULAR_PROFORMA",
                "fecha": "2026-10-07",
                "actor": "alvaro.huallpa",
                "posterior_a_fecha_preparacion": False,
                "orden_ejecucion": 13,
            }
        )

    pedidos_obj = [
        {
            "id": "EVAL-PED-01",
            "proforma_id": "EVAL-PF-01",
            "fecha_confirmacion": "2026-10-02",
            "estado_objetivo": "ENTREGADO",
            "total": "2800.00",
            "fecha_entrega_programada": "2026-12-10",
            "fecha_entrega_simulada": "2026-10-06",
        },
        {
            "id": "EVAL-PED-02",
            "proforma_id": "EVAL-PF-02",
            "fecha_confirmacion": "2026-10-03",
            "estado_objetivo": "CANCELADO",
            "total": "2700.00",
            "fecha_entrega_programada": "2027-01-05",
            "fecha_entrega_simulada": None,
        },
    ]
    ot_obj = [{"pedido_id": "EVAL-PED-01", "jefe_taller": "antonio.flores"}]
    recibos_obj = [
        {
            "id": "EVAL-REC-01",
            "pedido_id": "EVAL-PED-01",
            "fecha": "2026-10-02",
            "actor": "alvaro.huallpa",
            "tipo_pago": "EFECTIVO",
            "concepto": "Adelanto simulado",
            "pago_actual": recibo_pago,
            "estado": "EMITIDO",
        }
    ]
    notas_obj = [{"pedido_id": "EVAL-PED-01", "fecha_emision": "2026-10-05"}]
    movs_esp = []
    conc_stock = [
        {"sku": "EVAL-SILLA-01", "apertura": "10", "saldo_objetivo": "8"},
        {"sku": "EVAL-PISO-BP", "apertura": "0", "saldo_objetivo": "0"},
    ]
    resumen_val = {
        "corte_virtual": "2026-11-27",
        "clientes": 2,
        "proformas": 3,
        "pedidos": 2,
        "ordenes_trabajo_funcionales": 1,
        "recibos": 1,
        "notas": 1,
        "movimientos_venta": 2,
        "movimientos_reversa": 1,
        "stock_apertura": "10",
        "stock_cierre": "999" if oraculo_conciliacion_invalido else "8",
        "importe_pedidos_no_cancelados": "2800.00",
        "pagos_simulados": "900.00",
        "entregas_programadas_diciembre": 1,
        "entregas_programadas_enero": 1,
    }

    archivos = {
        "catalogo_escenario.json": catalogo,
        "clientes_ficticios.json": clientes,
        "plantillas_mueble.json": plantillas,
        "proformas.json": proformas,
        "eventos_cronologicos.json": eventos,
        "pedidos_objetivo.json": pedidos_obj,
        "ordenes_trabajo_objetivo.json": ot_obj,
        "recibos_objetivo.json": recibos_obj,
        "notas_entrega_objetivo.json": notas_obj,
        "movimientos_esperados.json": movs_esp,
        "conciliacion_stock.json": conc_stock,
        "resumen_validacion.json": resumen_val,
    }

    entradas_manifiesto = []
    zip_path = tmp_path / nombre
    with zipfile.ZipFile(zip_path, "w") as zf:
        for rel, payload in archivos.items():
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            zf.writestr(f"HOMEX_DATA_MASTER/12_escenario_evaluacion/{rel}", raw)
            sha = _sha256_bytes(raw)
            if corromper_sha and rel == "catalogo_escenario.json":
                sha = "0" * 64
            if omitir_obligatorio_en_manifiesto and rel == "conciliacion_stock.json":
                continue
            entradas_manifiesto.append({"ruta": rel, "sha256": sha})

        manifiesto = {"version": "0.4", "archivos": entradas_manifiesto}
        zf.writestr(
            "HOMEX_DATA_MASTER/12_escenario_evaluacion/manifiesto_escenario.json",
            json.dumps(manifiesto).encode("utf-8"),
        )
        if agregar_entrada_duplicada:
            zf.writestr(
                "HOMEX_DATA_MASTER/12_escenario_evaluacion/plantillas_mueble.json",
                b"[]",
            )
        if agregar_colision_normalizada:
            zf.writestr(
                "12_escenario_evaluacion/plantillas_mueble.json",
                b"[]",
            )
        if agregar_zip_slip:
            zf.writestr("../escape.txt", b"malicioso")
        if agregar_symlink:
            zi = zipfile.ZipInfo("HOMEX_DATA_MASTER/12_escenario_evaluacion/link")
            zi.create_system = 3
            zi.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(zi, b"/etc/passwd")

    return zip_path


def _construir_zip_documental(tmp_path: Path) -> Path:
    img_bytes = b"fake-jpeg-data"
    img_sha = _sha256_bytes(img_bytes)
    incidencias = [
        {
            "id_incidencia": "INC-001",
            "id_fuente": "A-001",
            "codigo": "PRECIO_PENDIENTE",
            "nivel": "BLOQUEANTE",
            "estado_resolucion": "PENDIENTE_VALIDACION",
            "detalle": "Sin precio confirmado",
            "decision": "No importar",
        },
        {
            "id_incidencia": "INC-002",
            "id_fuente": "A-002",
            "codigo": "NUMERO_AUSENTE",
            "nivel": "REVISAR",
            "estado_resolucion": "RESUELTA_REGLA_DOCUMENTAL",
            "detalle": "Sin número",
            "decision": "Mantener fuente",
        },
    ]
    imagenes_mapeo = [
        {
            "archivo": "imagenes_candidatas/img1.jpg",
            "sha256": img_sha,
            "estado": "CANDIDATA_NO_VALIDADA",
        }
    ]
    base_files = {
        "01_catalogo/imagenes_mapeo.json": json.dumps(imagenes_mapeo).encode("utf-8"),
        "01_catalogo/imagenes_candidatas/img1.jpg": img_bytes,
    }
    res_files = {
        "reglas_importacion.json": json.dumps({"default_mode": "dry-run"}).encode("utf-8"),
        "incidencias_decisiones.json": json.dumps(incidencias).encode("utf-8"),
        "productos_decisiones.json": json.dumps(
            [{"sku": "B15", "habilitar_venta_automatica": False}]
        ).encode("utf-8"),
        "clientes_decisiones.json": json.dumps([{"id_cliente": "CLI-1"}]).encode("utf-8"),
        "proformas_decisiones.json": json.dumps(
            [{"id_grupo": "PR-1", "importacion_operativa_autorizada": False}]
        ).encode("utf-8"),
        "notas_decisiones.json": json.dumps(
            [{"id_fuente": "A-002", "crear_pedido_o_nota_operativa": False}]
        ).encode("utf-8"),
    }

    zip_path = tmp_path / "doc_test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        manifiesto_base = {"version": "0.2", "archivos": []}
        for rel, raw in base_files.items():
            zf.writestr(f"HOMEX_DATA_MASTER/{rel}", raw)
            manifiesto_base["archivos"].append({"ruta": rel, "sha256": _sha256_bytes(raw)})
        zf.writestr(
            "HOMEX_DATA_MASTER/manifiesto.json",
            json.dumps(manifiesto_base).encode("utf-8"),
        )

        manifiesto_res = {"archivos_resolucion": {}}
        for rel, raw in res_files.items():
            zf.writestr(f"HOMEX_DATA_MASTER/11_resolucion/{rel}", raw)
            manifiesto_res["archivos_resolucion"][rel] = _sha256_bytes(raw)
        zf.writestr(
            "HOMEX_DATA_MASTER/11_resolucion/manifiesto_resolucion.json",
            json.dumps(manifiesto_res).encode("utf-8"),
        )
    return zip_path


@pytest.fixture
def actores_comerciales(db):
    g_enc, _ = Group.objects.get_or_create(name="ENCARGADO_TIENDA")
    g_jef, _ = Group.objects.get_or_create(name="JEFE_TALLER")
    ana = User.objects.create_user(username="ana.huallpara", password="x", is_staff=True)
    alvaro = User.objects.create_user(username="alvaro.huallpa", password="x")
    alvaro.groups.add(g_enc)
    rodrigo = User.objects.create_user(username="rodrigo.ramos", password="x")
    rodrigo.groups.add(g_enc)
    antonio = User.objects.create_user(username="antonio.flores", password="x")
    antonio.groups.add(g_jef)
    return {"ana": ana, "alvaro": alvaro, "rodrigo": rodrigo, "antonio": antonio}


@pytest.mark.django_db
def test_dry_run_predeterminado_no_persiste_efectos(tmp_path, actores_comerciales):
    zip_path = _construir_zip_escenario(tmp_path)
    out = io.StringIO()
    call_command(
        "importar_datos_homex",
        str(zip_path),
        "--perfil",
        "escenario",
        "--fecha-corte",
        "2026-11-27",
        "--simular-reloj-virtual",
        stdout=out,
    )
    reporte = json.loads(out.getvalue())
    assert reporte["modo"] == "DRY_RUN"
    assert reporte["auditoria"]["conforme"] is True
    assert Producto.objects.filter(sku__startswith="EVAL-").count() == 0
    assert Cliente.objects.count() == 0
    assert Proforma.objects.count() == 0


@pytest.mark.django_db
def test_importacion_completa_idempotencia_y_auditoria(tmp_path, actores_comerciales):
    zip_path = _construir_zip_escenario(tmp_path)
    reporte_path = tmp_path / "reporte.json"

    out = io.StringIO()
    call_command(
        "importar_datos_homex",
        str(zip_path),
        "--perfil",
        "escenario",
        "--fecha-corte",
        "2026-11-27",
        "--simular-reloj-virtual",
        "--autorizar-importacion",
        "--reporte-json",
        str(reporte_path),
        stdout=out,
    )
    reporte = json.loads(reporte_path.read_text(encoding="utf-8"))
    assert reporte["modo"] == "PERSISTENTE"
    assert reporte["auditoria"]["conforme"] is True
    assert reporte["auditoria"]["metricas"]["stock_inicial"] == "10"
    assert reporte["auditoria"]["metricas"]["stock_final"] == "8"
    assert reporte["auditoria"]["metricas"]["bajo_pedido_con_stock"] == 0
    assert Producto.objects.get(sku="EVAL-PISO-BP").stock == Decimal("0")
    assert Pedido.objects.count() == 2
    assert OrdenTrabajo.objects.count() == 2
    assert Recibo.objects.count() == 1
    assert NotaEntrega.objects.count() == 1
    assert MovimientoStock.objects.filter(tipo_movimiento__codigo="VENTA").count() == 2
    assert MovimientoStock.objects.filter(tipo_movimiento__codigo="REVERSA_VENTA").count() == 1

    # Las marcas de auditoría reales (creado_en) no se alteran al pasado
    pf1 = Proforma.objects.get(observaciones__contains="EVAL-PF-01")
    assert pf1.fecha == date(2026, 10, 1)
    assert pf1.creado_en.date() == timezone.localdate()

    # Reejecución idempotente
    out_re = io.StringIO()
    call_command(
        "importar_datos_homex",
        str(zip_path),
        "--perfil",
        "escenario",
        "--fecha-corte",
        "2026-11-27",
        "--simular-reloj-virtual",
        "--autorizar-importacion",
        stdout=out_re,
    )
    rep_re = json.loads(out_re.getvalue())
    assert rep_re["eventos"]["ejecutados"] == 0
    assert rep_re["eventos"]["idempotentes"] == 12
    assert rep_re["auditoria"]["conforme"] is True

    # Auditoría posterior independiente
    out_aud = io.StringIO()
    call_command(
        "importar_datos_homex",
        str(zip_path),
        "--perfil",
        "escenario",
        "--fecha-corte",
        "2026-11-27",
        "--auditar",
        stdout=out_aud,
    )
    assert json.loads(out_aud.getvalue())["auditoria"]["conforme"] is True

    # Conflicto de idempotencia si se modifica el precio en la fuente
    zip_conflicto = _construir_zip_escenario(
        tmp_path, nombre="conflicto.zip", modificar_precio_en_reintento=True
    )
    with pytest.raises(CommandError, match="ya existe con datos comerciales distintos"):
        call_command(
            "importar_datos_homex",
            str(zip_conflicto),
            "--perfil",
            "escenario",
            "--fecha-corte",
            "2026-11-27",
            "--simular-reloj-virtual",
            "--autorizar-importacion",
        )


@pytest.mark.django_db
def test_rechaza_paquete_corrupto_zip_slip_y_symlink(tmp_path, actores_comerciales):
    for kwargs, patron in (
        ({"corromper_sha": True}, "SHA-256 inválido"),
        ({"agregar_zip_slip": True}, "path traversal"),
        ({"agregar_symlink": True}, "enlace simbólico"),
        ({"cliente_inexistente": True}, "cliente inexistente"),
    ):
        zip_path = _construir_zip_escenario(tmp_path, nombre=f"bad_{patron[:4]}.zip", **kwargs)
        with pytest.raises(CommandError, match=patron):
            call_command(
                "importar_datos_homex",
                str(zip_path),
                "--perfil",
                "escenario",
                "--fecha-corte",
                "2026-11-27",
                "--simular-reloj-virtual",
            )


@pytest.mark.django_db
def test_error_parcial_revierte_transaccion_y_fecha_corte_y_reloj(tmp_path, actores_comerciales):
    # Error al final provoca rollback completo
    zip_err = _construir_zip_escenario(tmp_path, nombre="err.zip", evento_invalido_al_final=True)
    with pytest.raises(CommandError):
        call_command(
            "importar_datos_homex",
            str(zip_err),
            "--perfil",
            "escenario",
            "--fecha-corte",
            "2026-11-27",
            "--simular-reloj-virtual",
            "--autorizar-importacion",
        )
    assert Producto.objects.filter(sku__startswith="EVAL-").count() == 0
    assert Proforma.objects.count() == 0

    # Sin --simular-reloj-virtual rechaza evento futuro
    zip_ok = _construir_zip_escenario(tmp_path, nombre="corte.zip")
    with pytest.raises(CommandError, match="simular-reloj-virtual"):
        call_command(
            "importar_datos_homex",
            str(zip_ok),
            "--perfil",
            "escenario",
            "--fecha-corte",
            "2026-11-27",
        )

    # Fecha de corte anterior excluye el evento futuro del 2026-11-26
    out = io.StringIO()
    call_command(
        "importar_datos_homex",
        str(zip_ok),
        "--perfil",
        "escenario",
        "--fecha-corte",
        "2026-10-10",
        stdout=out,
    )
    rep = json.loads(out.getvalue())
    assert rep["eventos"]["ejecutados"] == 11
    assert rep["eventos"]["excluidos_por_corte"] == 1


@pytest.mark.django_db
def test_perfil_documental_reporta_incidencias_sin_importar(tmp_path, actores_comerciales):
    zip_doc = _construir_zip_documental(tmp_path)
    out = io.StringIO()
    call_command(
        "importar_datos_homex",
        str(zip_doc),
        "--perfil",
        "documental",
        "--autorizar-importacion",
        stdout=out,
    )
    rep = json.loads(out.getvalue())
    assert rep["perfil"] == "documental"
    assert rep["operaciones_importadas"] == 0
    assert rep["incidencias"]["pendientes_excluidas"] == 1
    assert rep["imagenes"]["pendientes_asignacion"] == 1
    assert Proforma.objects.count() == 0


@pytest.mark.django_db
def test_rollback_integral_si_falla_conciliacion_final_persistente(tmp_path, actores_comerciales):
    zip_bad_oracle = _construir_zip_escenario(
        tmp_path,
        nombre="bad_oracle.zip",
        oraculo_conciliacion_invalido=True,
    )
    reporte_err = tmp_path / "reporte_fallo.json"
    with pytest.raises(CommandError, match="Conciliación con discrepancias"):
        call_command(
            "importar_datos_homex",
            str(zip_bad_oracle),
            "--perfil",
            "escenario",
            "--fecha-corte",
            "2026-11-27",
            "--simular-reloj-virtual",
            "--autorizar-importacion",
            "--reporte-json",
            str(reporte_err),
        )
    # Transacción completa revertida: cero registros comerciales persistidos
    assert Producto.objects.filter(sku__startswith="EVAL-").count() == 0
    assert Cliente.objects.count() == 0
    assert Proforma.objects.count() == 0
    assert Pedido.objects.count() == 0
    assert OrdenTrabajo.objects.count() == 0
    assert Recibo.objects.count() == 0
    assert NotaEntrega.objects.count() == 0
    assert MovimientoStock.objects.count() == 0
    assert json.loads(reporte_err.read_text(encoding="utf-8"))["auditoria"]["conforme"] is False


@pytest.mark.django_db
def test_proteccion_entorno_y_zip_duplicados_y_manifiesto_incompleto(
    tmp_path, actores_comerciales, monkeypatch, settings
):
    zip_ok = _construir_zip_escenario(tmp_path)

    # Bloquea settings.production
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.production")
    with pytest.raises(CommandError, match="config.settings.production"):
        call_command(
            "importar_datos_homex",
            str(zip_ok),
            "--perfil",
            "escenario",
            "--autorizar-importacion",
        )
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.test")

    # Bloquea bases no autorizadas (p.ej. homex_prod / homex_dev / otra base)
    db_orig = settings.DATABASES["default"]["NAME"]
    try:
        settings.DATABASES["default"]["NAME"] = "homex_prod"
        with pytest.raises(CommandError, match="no está autorizada"):
            call_command(
                "importar_datos_homex",
                str(zip_ok),
                "--perfil",
                "escenario",
                "--autorizar-importacion",
            )
    finally:
        settings.DATABASES["default"]["NAME"] = db_orig

    # Integridad ZIP: entrada duplicada, colisión normalizada y archivo obligatorio omitido
    for kwargs, patron in (
        ({"agregar_entrada_duplicada": True}, "Entrada duplicada"),
        ({"agregar_colision_normalizada": True}, "Colisión de ruta normalizada"),
        ({"omitir_obligatorio_en_manifiesto": True}, "sin cobertura"),
    ):
        bad_zip = _construir_zip_escenario(tmp_path, nombre=f"zip_{patron[:4]}.zip", **kwargs)
        with pytest.raises(CommandError, match=patron):
            call_command(
                "importar_datos_homex",
                str(bad_zip),
                "--perfil",
                "escenario",
                "--fecha-corte",
                "2026-11-27",
                "--simular-reloj-virtual",
            )
