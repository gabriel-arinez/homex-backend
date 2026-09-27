"""Verifica en PostgreSQL la evidencia producida por el frontend real durante F09."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.integration")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from apps.capturas.models import Captura, IntentoCaptura, ItemHumano, ItemIA  # noqa: E402
from apps.movimientos_stock.models import MovimientoStock  # noqa: E402
from apps.notas_entrega.models import NotaEntrega  # noqa: E402
from apps.ordenes_trabajo.models import OrdenTrabajo  # noqa: E402
from apps.pedidos.models import Pedido  # noqa: E402
from apps.proformas.models import EspecificacionMueble, Proforma  # noqa: E402
from apps.recibos.models import Recibo  # noqa: E402


def exigir(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise AssertionError(mensaje)


def ejecutar() -> None:
    comercial = Proforma.objects.get(titulo="Flujo comercial FE08")
    cancelable = Proforma.objects.get(titulo="Cancelación válida FE08")
    voz = Proforma.objects.get(titulo="Captura de voz FE08")
    pedido = Pedido.objects.get(proforma=comercial)
    pedido_cancelado = Pedido.objects.get(proforma=cancelable)

    exigir(comercial.estado.codigo == "APROBADA", "La proforma comercial no quedó APROBADA.")
    exigir(pedido.estado.codigo == "LISTO_ENTREGA", "El pedido no llegó a LISTO_ENTREGA.")
    exigir(pedido_cancelado.estado.codigo == "CANCELADO", "La cancelación válida no persistió.")
    exigir(OrdenTrabajo.objects.filter(pedido=pedido).exists(), "No se creó la OT automática.")
    exigir(
        MovimientoStock.objects.filter(
            producto__sku="FE08-SILLA-001", tipo_movimiento__codigo="VENTA"
        ).exists(),
        "No se persistió el movimiento VENTA.",
    )
    exigir(
        MovimientoStock.objects.filter(
            producto__sku="FE08-SILLA-001", tipo_movimiento__codigo="REVERSA_VENTA"
        ).exists(),
        "No se persistió la REVERSA_VENTA.",
    )
    exigir(
        Recibo.objects.filter(pedido=pedido, estado="ANULADO").exists(),
        "El recibo no conserva la anulación.",
    )
    exigir(NotaEntrega.objects.filter(pedido=pedido).exists(), "No se emitió la nota de entrega.")

    captura = Captura.objects.get(proforma=voz)
    intento = IntentoCaptura.objects.get(captura=captura)
    item_ia = ItemIA.objects.get(intento=intento)
    exigir(captura.estado == "COMPLETADA", "La captura no terminó COMPLETADA.")
    exigir(bool(captura.texto_transcrito), "No se persistió la transcripción ASR.")
    exigir(captura.proforma_detalle_id is not None, "La captura no se vinculó al detalle.")
    exigir(intento.estado == "FINALIZADO", "El intento NLP no terminó FINALIZADO.")
    exigir(bool(intento.modelo_asr_version), "No se registró la versión ASR.")
    exigir(bool(intento.resultado_raw), "No se conservó la evidencia NLP original.")
    exigir(ItemHumano.objects.filter(item_ia=item_ia).exists(), "No se persistió la revisión HITL.")
    exigir(
        EspecificacionMueble.objects.filter(
            proforma_detalle_id=captura.proforma_detalle_id
        ).exists(),
        "La confirmación HITL no creó la especificación comercial.",
    )
    exigir(voz.estado.codigo == "BORRADOR", "HITL aprobó indebidamente la proforma.")

    temporales = [ruta for ruta in settings.HOMEX_AUDIO_TEMP_ROOT.glob("*") if ruta.is_file()]
    exigir(not temporales, f"Quedaron audios temporales: {temporales}")

    print(
        "f09-frontend-backend-ok",
        f"pedido={pedido.id}",
        f"captura={captura.id}",
        "postgresql=ok audio-temporal=eliminado",
    )


if __name__ == "__main__":
    ejecutar()
