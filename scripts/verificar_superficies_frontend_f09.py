"""Ejercita documentos y media por la API pública sobre la evidencia del E2E F09."""

from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.integration")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from PIL import Image  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from apps.catalogo.models import Producto  # noqa: E402
from apps.notas_entrega.models import NotaEntrega  # noqa: E402
from apps.ordenes_trabajo.models import OrdenTrabajo  # noqa: E402
from apps.pedidos.models import Pedido  # noqa: E402
from apps.proformas.models import Proforma  # noqa: E402
from apps.recibos.models import Recibo  # noqa: E402


def imagen(nombre: str) -> SimpleUploadedFile:
    salida = BytesIO()
    Image.new("RGB", (640, 400), "#8b1e1e").save(salida, format="JPEG")
    return SimpleUploadedFile(nombre, salida.getvalue(), content_type="image/jpeg")


def exigir_respuesta(respuesta, estado: int, contexto: str) -> None:
    if respuesta.status_code != estado:
        raise AssertionError(f"{contexto}: HTTP {respuesta.status_code} {respuesta.content!r}")


def ejecutar() -> None:
    actor = get_user_model().objects.get(username="fe08-admin")
    comercial = Proforma.objects.get(titulo="Flujo comercial FE08")
    voz = Proforma.objects.get(titulo="Captura de voz FE08")
    pedido = Pedido.objects.get(proforma=comercial)
    orden = OrdenTrabajo.objects.get(pedido=pedido)
    recibo = Recibo.objects.get(pedido=pedido)
    nota = NotaEntrega.objects.get(pedido=pedido)
    producto = Producto.objects.get(sku="FE08-SILLA-001")

    cliente = APIClient(HTTP_HOST="127.0.0.1")
    cliente.force_authenticate(actor)
    documentos = [
        (
            f"/api/v1/proformas/{comercial.id}/documento/",
            f"proforma-{comercial.numero}.html",
            str(comercial.numero),
        ),
        (
            f"/api/v1/ordenes-trabajo/{orden.id}/documento/",
            f"orden-trabajo-{orden.numero}.html",
            str(orden.numero),
        ),
        (
            f"/api/v1/recibos/{recibo.id}/documento/",
            f"recibo-{recibo.numero}.html",
            str(recibo.numero),
        ),
        (
            f"/api/v1/notas-entrega/{nota.id}/documento/",
            f"nota-entrega-{nota.numero}.html",
            str(nota.numero),
        ),
    ]
    for url, nombre, evidencia in documentos:
        respuesta = cliente.get(url)
        exigir_respuesta(respuesta, 200, url)
        if not respuesta["Content-Type"].startswith("text/html"):
            raise AssertionError(f"{url} no devolvió HTML descargable.")
        if respuesta["Content-Disposition"] != f'attachment; filename="{nombre}"':
            raise AssertionError(f"{url} publicó un nombre de archivo inesperado.")
        if evidencia not in respuesta.content.decode():
            raise AssertionError(f"{url} no contiene su numeración persistida.")

    respuesta = cliente.post(
        f"/api/v1/catalogo/productos/{producto.id}/imagen-principal/",
        {"archivo": imagen("producto-f09.jpg")},
        format="multipart",
    )
    exigir_respuesta(respuesta, 201, "imagen principal")
    media = respuesta.data["imagen_principal"]
    if (media["ancho"], media["alto"]) != (640, 400):
        raise AssertionError("La API no publicó las dimensiones de la imagen normalizada.")
    if set(media["variantes"]) != {"320", "640"}:
        raise AssertionError("La API no publicó las variantes WebP esperadas.")
    exigir_respuesta(
        cliente.delete(f"/api/v1/catalogo/productos/{producto.id}/imagen-principal/"),
        204,
        "eliminar imagen principal",
    )

    detalle = voz.detalles.get()
    url_adjuntos = f"/api/v1/proformas/{voz.id}/detalles/{detalle.id}/archivos/"
    respuesta = cliente.post(
        url_adjuntos,
        {"archivo": imagen("referencia-f09.jpg")},
        format="multipart",
    )
    exigir_respuesta(respuesta, 201, "adjunto de proforma")
    adjunto_id = respuesta.data["id"]
    exigir_respuesta(cliente.get(url_adjuntos), 200, "listar adjuntos")
    exigir_respuesta(
        cliente.delete(f"{url_adjuntos}{adjunto_id}/"),
        204,
        "eliminar adjunto",
    )

    print("f09-public-surfaces-ok documentos=4 producto-media=ok proforma-media=ok")


if __name__ == "__main__":
    ejecutar()
