from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

from apps.documentos.pdf import _imagen_principal_detalle


def _foto_prueba():
    salida = BytesIO()
    Image.new("RGB", (800, 400), "white").save(salida, format="PNG")
    salida.seek(0)
    return salida


def test_portada_catalogo_preserva_proporciones():
    listado = MagicMock()
    listado.order_by.return_value.first.return_value = SimpleNamespace(
        ruta_storage="productos/foto.webp"
    )
    detalle = SimpleNamespace(
        producto_id=9,
        producto=SimpleNamespace(imagenes=listado),
    )
    with patch("apps.documentos.pdf.default_storage") as storage:
        storage.open.return_value = _foto_prueba()
        fotografia = _imagen_principal_detalle(detalle)

    assert fotografia is not None
    assert round(fotografia.drawWidth / fotografia.drawHeight, 2) == 2.0
    storage.open.assert_called_once_with("productos/foto.webp", "rb")


def test_portada_de_mueble_usa_almacenamiento_privado():
    adjunto = SimpleNamespace(ruta_storage="proformas/referencia.webp", privado=True)
    with (
        patch("apps.documentos.pdf.ArchivoAdjunto.objects.filter") as consulta,
        patch("apps.documentos.pdf.privado") as obtener_privado,
        patch("apps.documentos.pdf.default_storage") as publico,
    ):
        consulta.return_value.order_by.return_value.first.return_value = adjunto
        obtener_privado.return_value.open.return_value = _foto_prueba()
        fotografia = _imagen_principal_detalle(SimpleNamespace(producto_id=None, pk=7))

    assert fotografia is not None
    obtener_privado.return_value.open.assert_called_once_with("proformas/referencia.webp", "rb")
    publico.open.assert_not_called()
