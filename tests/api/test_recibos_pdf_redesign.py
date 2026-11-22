import shutil
import subprocess
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.db import close_old_connections
from rest_framework.test import APIClient

from apps.recibos.models import Recibo
from apps.recibos.services import anular_recibo
from tests.factories import valor, vendedor
from tests.integration.test_f074_cobros import crear_pedido_confirmado


def _admin(django_user_model, username="rec-admin"):
    return django_user_model.objects.create_user(username=username, is_staff=True)


def _extraer_texto_pdf(pdf_bytes: bytes) -> str | None:
    if not shutil.which("pdftotext"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf_bytes)
        f.flush()
        res = subprocess.run(
            ["pdftotext", f.name, "-"],
            check=True,
            capture_output=True,
            text=True,
        )
        return res.stdout


@pytest.mark.django_db(transaction=True)
def test_emision_idempotencia_validaciones_y_concurrencia(django_user_model):
    admin = _admin(django_user_model)
    vendedor_a = vendedor(django_user_model.objects.create_user(username="rec-vend-a"))
    vendedor_b = vendedor(django_user_model.objects.create_user(username="rec-vend-b"))
    pedido, _ = crear_pedido_confirmado(vendedor_a, sku="REC-SILLA-1", cantidad=2)
    efectivo = valor("TIPO_PAGO", "EFECTIVO")
    cheque = valor("TIPO_PAGO", "CHEQUE")

    c_a = APIClient()
    c_a.force_authenticate(vendedor_a)
    c_b = APIClient()
    c_b.force_authenticate(vendedor_b)

    # Aislamiento: otro vendedor no puede emitir recibo sobre pedido ajeno
    assert (
        c_b.post(
            f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
            {
                "nombre_completo": "Cliente",
                "monto_en_letras": "Diez 00/100 Bolivianos",
                "concepto": "Abono",
                "tipo_pago": efectivo.id,
                "pago_actual": "10.00",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        ).status_code
        == 404
    )

    # Validación monetaria: <= 0 o sobrepago -> 400
    for invalido in ("0.00", "-5.00", "9999.00"):
        assert (
            c_a.post(
                f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
                {
                    "nombre_completo": "Cliente Test",
                    "monto_en_letras": "Cero 00/100 Bolivianos",
                    "concepto": "Abono",
                    "tipo_pago": efectivo.id,
                    "pago_actual": invalido,
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 400
        )

    # Pago parcial idempotente (1ra vez -> 201, reintento idéntico -> 200)
    clave_1 = str(uuid.uuid4())
    payload_1 = {
        "nombre_completo": "Juan Pérez",
        "monto_en_letras": "Cuarenta 00/100 Bolivianos",
        "concepto": f"Abono Pedido #{pedido.id}",
        "tipo_pago": efectivo.id,
        "pago_actual": "40.00",
    }
    r1 = c_a.post(
        f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
        payload_1,
        format="json",
        HTTP_IDEMPOTENCY_KEY=clave_1,
    )
    assert r1.status_code == 201
    assert Decimal(r1.data["a_cuenta"]) == Decimal("40.00")
    assert Decimal(r1.data["saldo"]) == Decimal("60.00")
    assert r1.data["moneda_codigo"] == "BOB"

    r1_replay = c_a.post(
        f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
        payload_1,
        format="json",
        HTTP_IDEMPOTENCY_KEY=clave_1,
    )
    assert r1_replay.status_code == 200
    assert r1_replay.data["id"] == r1.data["id"]
    assert Recibo.objects.filter(pedido=pedido).count() == 1

    # Misma clave con datos distintos -> HTTP 409
    r1_conflict = c_a.post(
        f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
        {**payload_1, "pago_actual": "35.00"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=clave_1,
    )
    assert r1_conflict.status_code == 409

    # Misma clave reutilizada por distinto usuario (admin) -> HTTP 409
    c_admin = APIClient()
    c_admin.force_authenticate(admin)
    assert (
        c_admin.post(
            f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
            payload_1,
            format="json",
            HTTP_IDEMPOTENCY_KEY=clave_1,
        ).status_code
        == 409
    )

    # Concurrencia con misma Idempotency-Key para el saldo final con cheque -> [200, 201]
    clave_conc = str(uuid.uuid4())
    payload_cheque = {
        "nombre_completo": "Juan Pérez",
        "monto_en_letras": "Sesenta 00/100 Bolivianos",
        "concepto": f"Saldo final Pedido #{pedido.id}",
        "tipo_pago": cheque.id,
        "numero_cheque": "CHQ-8899",
        "banco": "Banco Nacional",
        "pago_actual": "60.00",
    }

    def _emitir_concurrente(_idx):
        close_old_connections()
        cli = APIClient()
        cli.force_authenticate(vendedor_a)
        return cli.post(
            f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
            payload_cheque,
            format="json",
            HTTP_IDEMPOTENCY_KEY=clave_conc,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codigos = sorted(pool.map(_emitir_concurrente, [1, 2]))

    assert codigos == [200, 201]
    assert Recibo.objects.filter(pedido=pedido).count() == 2
    ultimo = Recibo.objects.filter(pedido=pedido).order_by("-id").first()
    assert ultimo.saldo == Decimal("0.00")
    assert ultimo.a_cuenta == Decimal("100.00")


@pytest.mark.django_db(transaction=True)
def test_pdf_recibo_dos_copias_carta_anulado_y_textos_largos(django_user_model):
    admin = _admin(django_user_model, username="rec-pdf-admin")
    vend_otro = vendedor(django_user_model.objects.create_user(username="rec-pdf-otro"))
    pedido, _ = crear_pedido_confirmado(admin, sku="REC-PDF-1", cantidad=2)
    cheque = valor("TIPO_PAGO", "CHEQUE")

    c_admin = APIClient()
    c_admin.force_authenticate(admin)
    r_create = c_admin.post(
        f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
        {
            "nombre_completo": "Empresa Constructora e Inmobiliaria del Altiplano Sociedad Anónima",
            "monto_en_letras": (
                "Cien 00/100 Bolivianos con descripción extendida para validar ajuste automático"
            ),
            "concepto": (
                "Pago correspondiente a mobiliario corporativo de oficina con entrega programada "
                "y especificaciones técnicas acordadas según proforma aprobada"
            ),
            "tipo_pago": cheque.id,
            "numero_cheque": "CHQ-990011",
            "banco": "Banco Mercantil Santa Cruz",
            "pago_actual": "100.00",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert r_create.status_code == 201
    recibo_id = r_create.data["id"]

    # Permisos: otro vendedor recibe 404, anónimo recibe 401
    assert APIClient().get(f"/api/v1/recibos/{recibo_id}/documento-pdf/").status_code == 401
    c_otro = APIClient()
    c_otro.force_authenticate(vend_otro)
    assert c_otro.get(f"/api/v1/recibos/{recibo_id}/documento-pdf/").status_code == 404

    r_pdf = c_admin.get(f"/api/v1/recibos/{recibo_id}/documento-pdf/")
    assert r_pdf.status_code == 200
    assert r_pdf["Content-Type"] == "application/pdf"
    assert f'filename="recibo-{r_create.data["numero"]}.pdf"' in r_pdf["Content-Disposition"]
    assert "no-store" in r_pdf["Cache-Control"]
    assert r_pdf.content.startswith(b"%PDF-")
    # Hoja carta vertical (612 x 792 pt) y exactamente 1 página
    assert b"/MediaBox [ 0 0 612 792 ]" in r_pdf.content
    assert b"/Count 1" in r_pdf.content

    texto = _extraer_texto_pdf(r_pdf.content)
    if texto is not None:
        assert "COPIA CLIENTE" not in texto
        assert "COPIA HOMEX" not in texto
        assert "Cortar por la línea punteada" not in texto
        assert "Firma del pagador" in texto
        assert "Recibí conforme" in texto

    # Recibo anulado conserva sus datos e incluye marca ANULADO en el PDF
    anular_recibo(recibo_id=recibo_id, actor=admin)
    r_pdf_anulado = c_admin.get(f"/api/v1/recibos/{recibo_id}/documento-pdf/")
    assert r_pdf_anulado.status_code == 200
    assert b"/Count 1" in r_pdf_anulado.content
    texto_anulado = _extraer_texto_pdf(r_pdf_anulado.content)
    if texto_anulado is not None:
        assert "ANULADO" in texto_anulado
        assert "COPIA CLIENTE" not in texto_anulado
        assert "COPIA HOMEX" not in texto_anulado


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("codigo", "nombre"),
    [("QR", "QR"), ("DEPOSITO", "Depósito"), ("TARJETA", "Tarjeta")],
)
def test_nuevos_tipos_pago_qr_deposito_tarjeta(django_user_model, codigo, nombre):
    admin = _admin(django_user_model, username=f"rec-tp-{codigo.lower()}")
    pedido, _ = crear_pedido_confirmado(admin, sku=f"REC-TP-{codigo}", cantidad=2)
    tipo = valor("TIPO_PAGO", codigo)
    assert tipo.nombre == nombre

    c = APIClient()
    c.force_authenticate(admin)
    resp = c.post(
        f"/api/v1/pedidos/{pedido.id}/emitir_recibo/",
        {
            "nombre_completo": "Cliente Pagador",
            "monto_en_letras": "Cincuenta 00/100 Bolivianos",
            "concepto": f"Cobro con {nombre}",
            "tipo_pago": tipo.id,
            "pago_actual": "50.00",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert resp.status_code == 201
    assert resp.data["tipo_pago_nombre"] == nombre
    assert resp.data["numero_cheque"] is None
    assert resp.data["banco"] is None

    r_pdf = c.get(f"/api/v1/recibos/{resp.data['id']}/documento-pdf/")
    assert r_pdf.status_code == 200
    assert r_pdf.content.startswith(b"%PDF-")
