"""Regresiones del documento editorial: no tocar cálculo ni estados."""

from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image as PILImage
from reportlab.lib.units import mm
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import Paragraph

from apps.documentos.pdf import renderizar_proforma_pdf
from apps.proformas.models import EspecificacionMueble
from apps.proformas.services import agregar_detalle, crear_proforma
from tests.factories import cliente_persona, valor, vendedor


@pytest.mark.django_db(transaction=True)
def test_documento_editorial_sin_foto_sin_descuentos_ni_subtotal_repetido(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="editorial-pdf"))
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="escritorio ejecutivo",
        descripcion="Escritorio de trabajo con repisas laterales.",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("1450.00"),
        descuento=Decimal("0.00"),
    )
    EspecificacionMueble.objects.create(
        proforma_detalle=detalle,
        datos_tecnicos={
            "caracteristicas_generales": {"material": "Melamina"},
            "componentes": [{"nombre": "Repisas", "material": "Melamina"}],
        },
        observaciones="Sin cajones.",
    )
    with patch("apps.documentos.pdf.Paragraph", wraps=Paragraph) as parrafos:
        pdf = renderizar_proforma_pdf(proforma.id, usuario=actor)

    textos = [call.args[0] for call in parrafos.call_args_list if call.args]
    assert pdf.startswith(b"%PDF")
    assert b"/MediaBox [ 0 0 612 792 ]" in pdf
    assert any("TOTAL COTIZADO" in str(texto) for texto in textos)
    assert not any("Subtotal general" in str(texto) for texto in textos)
    assert not any("Descuento global" in str(texto) for texto in textos)
    assert not any("Imagen de referencia pendiente" in str(texto) for texto in textos)
    assert any("Firma del cliente" in str(texto) for texto in textos)
    assert any("escritorio ejecutivo" in str(texto).lower() for texto in textos)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("tamano", [(900, 300), (300, 900), (500, 500)])
def test_documento_editorial_adapta_fotografias_sin_deformarlas(django_user_model, tamano):
    actor = vendedor(
        django_user_model.objects.create_user(username=f"foto-{tamano[0]}-{tamano[1]}")
    )
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Mesa con fotografía",
        cantidad=2,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("800.00"),
        descuento=Decimal("0.00"),
    )
    original = BytesIO()
    PILImage.new("RGB", tamano, (255, 255, 255)).save(original, "PNG")
    datos = original.getvalue()

    def portada(_detalle):
        proporcion = 44 * mm / max(tamano)
        return PdfImage(BytesIO(datos), width=tamano[0] * proporcion, height=tamano[1] * proporcion)

    with patch("apps.documentos.pdf._imagen_principal_detalle", side_effect=portada):
        pdf = renderizar_proforma_pdf(proforma.id, usuario=actor)
    assert pdf.startswith(b"%PDF")
    assert b"/MediaBox [ 0 0 612 792 ]" in pdf


@pytest.mark.django_db(transaction=True)
def test_documento_editorial_incluye_fichas_completas_de_catalogo_y_preserva_importes_proforma(
    django_user_model,
):
    from apps.catalogo.models import (
        ConceptoCatalogo,
        FamiliaProducto,
        Producto,
        ProductoPiso,
        ProductoSilla,
        ValorCatalogo,
    )

    actor = vendedor(django_user_model.objects.create_user(username="catalogo-pdf-completo"))

    def cat_val(concepto_cod, codigo, nombre):
        c, _ = ConceptoCatalogo.objects.get_or_create(
            codigo=concepto_cod, defaults={"activo": True}
        )
        v, _ = ValorCatalogo.objects.get_or_create(
            concepto=c, codigo=codigo, defaults={"nombre": nombre, "activo": True}
        )
        return v

    marca_silla = cat_val("MARCA", "HERMAN", "Herman Miller")
    color_negro = cat_val("COLOR", "GRAFITO", "Grafito")
    color_gris = cat_val("COLOR", "ALUMINIO", "Aluminio")
    familia_silla = FamiliaProducto.objects.create(
        codigo="FAM-AERON", nombre="Colección Aeron", activo=True
    )
    prod_silla = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "SILLA"),
        familia=familia_silla,
        sku="SIL-AER-01",
        nombre="Silla Aeron Maestro",
        precio_lista=Decimal("9500.00"),
        unidad_stock=valor("UNIDAD_MEDIDA", "PIEZA"),
        observaciones="Garantía oficial de 12 años.",
        created_by=actor,
        updated_by=actor,
    )
    ProductoSilla.objects.create(
        producto=prod_silla,
        marca=marca_silla,
        modelo="Aeron Remastered",
        color_primario=color_negro,
        color_secundario=color_gris,
        especificaciones={
            "soporte_lumbar": "PostureFit SL",
            "brazos": "Regulables 4D",
            "mecanismo": {"inclinacion": "Harmonic 2", "limitador": True},
        },
        created_by=actor,
        updated_by=actor,
    )

    marca_piso = cat_val("MARCA", "EGGER", "Egger")
    tipo_piso = cat_val("TIPO_PISO", "LAMINADO_AC5", "Laminado AC5")
    mat_piso = cat_val("MATERIAL_PISO", "HDF_CORE", "HDF Alta Densidad")
    dis_piso = cat_val("DISENO_PISO", "ROBLE_BARDOLINO", "Roble Bardolino")
    acab_piso = cat_val("ACABADO_PISO", "PORO_SINCRONIZADO", "Poro Sincronizado")
    prod_piso = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "PISO_FLOTANTE"),
        sku="PIS-EGG-10",
        nombre="Piso Flotante Roble Bardolino",
        precio_lista=Decimal("210.00"),
        unidad_stock=valor("UNIDAD_MEDIDA", "M2"),
        observaciones="Instalación flotante con sistema clic.",
        created_by=actor,
        updated_by=actor,
    )
    ProductoPiso.objects.create(
        producto=prod_piso,
        marca=marca_piso,
        modelo="EPL-035",
        tipo=tipo_piso,
        material=mat_piso,
        diseno=dis_piso,
        acabado=acab_piso,
        espesor_mm=Decimal("10.00"),
        largo_mm=Decimal("1292.00"),
        ancho_mm=Decimal("193.00"),
        m2_por_caja=Decimal("1.7450"),
        created_by=actor,
        updated_by=actor,
    )

    prod_otro = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "OTRO"),
        sku="OTR-ZOC-05",
        nombre="Zócalo Laminado 2,40 m",
        precio_lista=Decimal("65.00"),
        unidad_stock=valor("UNIDAD_MEDIDA", "BARRA"),
        observaciones="Incluye canal posterior para cableado.",
        created_by=actor,
        updated_by=actor,
    )

    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto=prod_silla,
        nombre="Silla Aeron Cotizada Especial",
        descripcion="Configuración especial para gerencia.",
        cantidad=Decimal("2"),
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("8200.00"),
        descuento=Decimal("400.00"),
    )
    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "PISO_FLOTANTE"),
        producto=prod_piso,
        nombre="Piso Flotante Roble Bardolino",
        descripcion=None,
        cantidad=Decimal("34.9000"),
        unidad=valor("UNIDAD_MEDIDA", "M2"),
        precio_unitario=Decimal("195.00"),
        descuento=Decimal("0.00"),
    )
    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "OTRO"),
        producto=prod_otro,
        nombre="Zócalo Laminado 2,40 m",
        descripcion="Color combinable con piso Roble Bardolino.",
        cantidad=Decimal("15"),
        unidad=valor("UNIDAD_MEDIDA", "BARRA"),
        precio_unitario=Decimal("60.00"),
        descuento=Decimal("0.00"),
    )

    # Modify catalogue prices afterwards to prove proforma persisted amounts are preserved
    prod_silla.precio_lista = Decimal("12000.00")
    prod_silla.save(update_fields=["precio_lista"])

    with patch("apps.documentos.pdf.Paragraph", wraps=Paragraph) as parrafos:
        pdf = renderizar_proforma_pdf(proforma.id, usuario=actor)

    texto_completo = "\n".join(str(call.args[0]) for call in parrafos.call_args_list if call.args)
    assert pdf.startswith(b"%PDF")
    for esperado in [
        "SIL-AER-01",
        "Colección Aeron",
        "Herman Miller",
        "Aeron Remastered",
        "Grafito",
        "Aluminio",
        "Silla Aeron Maestro",
        "PostureFit SL",
        "Regulables 4D",
        "Harmonic 2",
        "Configuración especial para gerencia.",
        "Garantía oficial de 12 años.",
        "Bs 8.200,00",
        "PIS-EGG-10",
        "Egger",
        "EPL-035",
        "Laminado AC5",
        "HDF Alta Densidad",
        "Roble Bardolino",
        "Poro Sincronizado",
        "10 mm",
        "1292 mm",
        "193 mm",
        "1,745 m²",
        "Instalación flotante con sistema clic.",
        "OTR-ZOC-05",
        "<b>Unidad de venta:</b> Barra",
        "Color combinable con piso Roble Bardolino.",
        "Incluye canal posterior para cableado.",
    ]:
        assert esperado in texto_completo
    assert "Bs 12.000,00" not in texto_completo
    assert "Bs 9.500,00" not in texto_completo


@pytest.mark.django_db(transaction=True)
def test_documento_editorial_catalogo_con_imagen_opcionales_y_codigos_tecnicos(
    django_user_model, tmp_path, settings
):
    import shutil
    import subprocess

    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from apps.catalogo.models import (
        ConceptoCatalogo,
        ImagenProducto,
        Producto,
        ProductoPiso,
        ProductoSilla,
        ValorCatalogo,
    )

    settings.MEDIA_ROOT = tmp_path
    actor = vendedor(django_user_model.objects.create_user(username="catalogo-pdf-img"))
    concepto_marca, _ = ConceptoCatalogo.objects.get_or_create(
        codigo="MARCA", defaults={"activo": True}
    )
    marca, _ = ValorCatalogo.objects.get_or_create(
        concepto=concepto_marca,
        codigo="STEELCASE",
        defaults={"nombre": "Steelcase", "activo": True},
    )
    concepto_color, _ = ConceptoCatalogo.objects.get_or_create(
        codigo="COLOR", defaults={"activo": True}
    )
    color, _ = ValorCatalogo.objects.get_or_create(
        concepto=concepto_color, codigo="AZUL", defaults={"nombre": "Azul Marino", "activo": True}
    )

    prod_silla = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "SILLA"),
        sku="SIL-IMG-01",
        nombre="Silla Leap con Imagen",
        precio_lista=Decimal("4500.00"),
        unidad_stock=valor("UNIDAD_MEDIDA", "PIEZA"),
        observaciones=None,
        created_by=actor,
        updated_by=actor,
    )
    ProductoSilla.objects.create(
        producto=prod_silla,
        marca=marca,
        modelo="Leap V2",
        color_primario=color,
        color_secundario=None,
        especificaciones={
            "certificacion": {"valor": "Ergonómica", "codigo": "BIFMA-G1"},
            "reclinable": False,
            "altura_min_extra": 0,
            **{f"prop_{i:02d}": f"Valor persistido {i:02d} " * 8 for i in range(18)},
        },
        created_by=actor,
        updated_by=actor,
    )
    img_buf = BytesIO()
    PILImage.new("RGB", (320, 240), "#1e293b").save(img_buf, "PNG")
    storage_key = default_storage.save("productos/leap-v2.png", ContentFile(img_buf.getvalue()))
    ImagenProducto.objects.create(
        producto=prod_silla,
        nombre="leap-v2.png",
        ruta_storage=storage_key,
        principal=True,
        posicion=0,
    )

    prod_piso = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "PISO_FLOTANTE"),
        sku="PIS-OPT-02",
        nombre="Piso Minimal Sin Opcionales",
        precio_lista=Decimal("130.00"),
        unidad_stock=valor("UNIDAD_MEDIDA", "M2"),
        observaciones=None,
        created_by=actor,
        updated_by=actor,
    )
    ProductoPiso.objects.create(
        producto=prod_piso,
        marca=marca,
        modelo=None,
        tipo=None,
        material=None,
        diseno=None,
        acabado=None,
        espesor_mm=Decimal("8.00"),
        largo_mm=None,
        ancho_mm=None,
        m2_por_caja=None,
        created_by=actor,
        updated_by=actor,
    )

    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "SILLA"),
        producto=prod_silla,
        nombre="Silla Leap con Imagen",
        cantidad=Decimal("1"),
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("4500.00"),
    )
    agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "PISO_FLOTANTE"),
        producto=prod_piso,
        nombre="Piso Minimal Sin Opcionales",
        cantidad=Decimal("10.0000"),
        unidad=valor("UNIDAD_MEDIDA", "M2"),
        precio_unitario=Decimal("130.00"),
    )

    with patch("apps.documentos.pdf.Paragraph", wraps=Paragraph) as parrafos:
        pdf = renderizar_proforma_pdf(proforma.id, usuario=actor)

    texto_completo = "\n".join(str(call.args[0]) for call in parrafos.call_args_list if call.args)
    assert pdf.startswith(b"%PDF")
    assert pdf.count(b"/Type /Page") >= 2
    for esperado in [
        "SIL-IMG-01",
        "Steelcase",
        "Leap V2",
        "Azul Marino",
        "BIFMA-G1",
        "<b>Reclinable:</b> No",
        "<b>Altura min extra:</b> 0",
        "Valor persistido 17",
        "PIS-OPT-02",
        "8 mm",
    ]:
        assert esperado in texto_completo
    assert "Color secundario" not in texto_completo
    assert "Rendimiento por caja" not in texto_completo

    if shutil.which("pdftotext"):
        pdf_file = tmp_path / "persisted_catalog.pdf"
        pdf_file.write_bytes(pdf)
        extracted = subprocess.check_output(["pdftotext", str(pdf_file), "-"], text=True)
        assert "SIL-IMG-01" in extracted
        assert "BIFMA-G1" in extracted
        assert "Valor persistido 17" in extracted
        assert "PIS-OPT-02" in extracted
