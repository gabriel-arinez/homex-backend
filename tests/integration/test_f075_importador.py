import pytest
from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.catalogo.importador import ErrorCatalogo, importar_catalogo
from apps.catalogo.models import (
    ConceptoCatalogo,
    Producto,
    ProductoPiso,
    ValorCatalogo,
)
from apps.movimientos_stock.models import MovimientoStock
from tests.factories import valor, vendedor
from tests.integration.test_f073_ventas import ejecutar_en_paralelo


@pytest.fixture(autouse=True)
def valores_comerciales_f075(db):
    valores = {
        "MARCA": {
            "MARCA_TEST": "Marca Test",
        },
        "COLOR": {
            "NEGRO": "Negro",
            "GRIS": "Gris",
        },
        "TIPO_PISO": {
            "LAMINADO": "Laminado",
        },
        "MATERIAL_PISO": {
            "HDF": "HDF",
        },
        "DISENO_PISO": {
            "MADERA": "Madera",
        },
        "ACABADO_PISO": {
            "MATE": "Mate",
        },
    }

    for concepto_codigo, opciones in valores.items():
        concepto, _ = ConceptoCatalogo.objects.get_or_create(
            codigo=concepto_codigo,
            defaults={
                "descripcion": f"Valores de prueba {concepto_codigo}",
                "activo": True,
            },
        )

        for codigo, nombre in opciones.items():
            ValorCatalogo.objects.get_or_create(
                concepto=concepto,
                codigo=codigo,
                defaults={
                    "nombre": nombre,
                    "activo": True,
                },
            )


def catalogo(sku="IMPORT-1", **cambios):
    producto = {
        "sku": sku,
        "categoria": "SILLA",
        "nombre": "Silla importada",
        "precio_lista": "1500.00",
        "stock_inicial": 8,
        "unidad_stock": "PIEZA",
        "ficha": {
            "marca": "MARCA_TEST",
            "modelo": "B15",
            "color_primario": "NEGRO",
            "color_secundario": "GRIS",
            "especificaciones": {
                "respaldo": "malla",
            },
        },
    }
    producto.update(cambios)
    return {
        "schema_version": 1,
        "productos": [producto],
    }


@pytest.mark.django_db(transaction=True)
def test_importador_dry_run_no_persiste(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="import-dry"))
    resultado = importar_catalogo(datos=catalogo(), actor=actor, dry_run=True)
    assert resultado.creados == 1
    assert not Producto.objects.filter(sku="IMPORT-1").exists()


@pytest.mark.django_db(transaction=True)
def test_importador_crea_stock_e_idempotencia(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="import-ok"))
    resultado = importar_catalogo(datos=catalogo(), actor=actor)
    producto = Producto.objects.get(sku="IMPORT-1")
    assert (resultado.creados, resultado.movimientos_stock, producto.stock) == (1, 1, 8)
    repeticion = importar_catalogo(datos=catalogo(), actor=actor)
    assert (repeticion.creados, repeticion.existentes, repeticion.movimientos_stock) == (0, 1, 0)
    producto.refresh_from_db()
    assert producto.stock == 8


@pytest.mark.django_db(transaction=True)
def test_importador_rechaza_duplicado_y_hace_rollback(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="import-error"))
    datos = catalogo()
    datos["productos"].append(datos["productos"][0].copy())
    with pytest.raises(ErrorCatalogo, match="SKU duplicados"):
        importar_catalogo(datos=datos, actor=actor)
    assert Producto.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_importador_rechaza_ficha_incompleta_y_jsonl(django_user_model, tmp_path):
    actor = vendedor(django_user_model.objects.create_user(username="import-jsonl"))
    with pytest.raises(ErrorCatalogo, match="ficha"):
        importar_catalogo(datos=catalogo(ficha=None), actor=actor)
    from apps.catalogo.importador import cargar_archivo_catalogo

    archivo = tmp_path / "sillas.jsonl"
    archivo.write_text('{"text":"B15"}\n', encoding="utf-8")
    with pytest.raises(ErrorCatalogo, match="JSON comercial"):
        cargar_archivo_catalogo(archivo)


@pytest.mark.django_db(transaction=True)
def test_importador_revierte_el_lote_completo_si_un_item_falla(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="import-rollback"))
    datos = catalogo()
    datos["productos"].append(
        {
            "sku": "IMPORT-INVALIDO",
            "categoria": "CATEGORIA_INEXISTENTE",
            "nombre": "No debe persistir",
            "precio_lista": "10.00",
            "stock_inicial": 1,
            "unidad_stock": "PIEZA",
        }
    )
    with pytest.raises(ErrorCatalogo, match="CATEGORIA_PRODUCTO"):
        importar_catalogo(datos=datos, actor=actor)
    assert Producto.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_carga_inicial_no_puede_repetirse_directamente(django_user_model):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="import-carga-unica",
        )
    )

    producto = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "SILLA"),
        sku="IMPORT-CARGA-UNICA",
        nombre="Producto carga única",
        precio_lista="100.00",
        stock=0,
        unidad_stock=valor("UNIDAD_MEDIDA", "PIEZA"),
        created_by=actor,
        updated_by=actor,
    )

    tipo_carga = valor(
        "TIPO_MOVIMIENTO",
        "CARGA_INICIAL",
    )

    MovimientoStock.objects.create(
        producto=producto,
        fecha=timezone.now(),
        tipo_movimiento=tipo_carga,
        cantidad=8,
        created_by=actor,
    )

    producto.refresh_from_db()
    assert producto.stock == 8

    with pytest.raises(
        DatabaseError,
        match="ya tiene una CARGA_INICIAL registrada",
    ):
        with transaction.atomic():
            MovimientoStock.objects.create(
                producto=producto,
                fecha=timezone.now(),
                tipo_movimiento=tipo_carga,
                cantidad=5,
                created_by=actor,
            )

    producto.refresh_from_db()

    assert producto.stock == 8
    assert (
        MovimientoStock.objects.filter(
            producto=producto,
            tipo_movimiento=tipo_carga,
        ).count()
        == 1
    )


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_carga_inicial_concurrente_solo_permite_una(django_user_model):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="import-carga-concurrente",
        )
    )

    producto = Producto.objects.create(
        categoria=valor("CATEGORIA_PRODUCTO", "SILLA"),
        sku="IMPORT-CARGA-CONCURRENTE",
        nombre="Producto carga concurrente",
        precio_lista="100.00",
        stock=0,
        unidad_stock=valor("UNIDAD_MEDIDA", "PIEZA"),
        created_by=actor,
        updated_by=actor,
    )

    tipo_carga = valor(
        "TIPO_MOVIMIENTO",
        "CARGA_INICIAL",
    )

    def cargar(cantidad):
        return MovimientoStock.objects.create(
            producto_id=producto.id,
            fecha=timezone.now(),
            tipo_movimiento_id=tipo_carga.id,
            cantidad=cantidad,
            created_by_id=actor.id,
        )

    resultados = ejecutar_en_paralelo(
        [
            ("carga-uno", lambda: cargar(8)),
            ("carga-dos", lambda: cargar(5)),
        ]
    )

    exitos = [resultado for resultado in resultados if resultado[1] == "ok"]
    errores = [resultado for resultado in resultados if resultado[1] == "error"]

    assert len(exitos) == 1
    assert len(errores) == 1
    assert isinstance(errores[0][2], DatabaseError)
    assert "ya tiene una CARGA_INICIAL registrada" in str(errores[0][2])

    producto.refresh_from_db()

    movimiento = MovimientoStock.objects.get(
        producto=producto,
        tipo_movimiento=tipo_carga,
    )

    assert (
        MovimientoStock.objects.filter(
            producto=producto,
            tipo_movimiento=tipo_carga,
        ).count()
        == 1
    )

    assert producto.stock == movimiento.cantidad
    assert producto.stock in (5, 8)


@pytest.mark.django_db(transaction=True)
def test_importador_rechaza_silla_sin_marca_o_color(django_user_model):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="import-silla-incompleta",
        )
    )

    sin_marca = catalogo()
    sin_marca["productos"][0]["ficha"].pop("marca")

    with pytest.raises(
        ErrorCatalogo,
        match=r"ficha\.marca",
    ):
        importar_catalogo(
            datos=sin_marca,
            actor=actor,
        )

    sin_color = catalogo(
        sku="IMPORT-SIN-COLOR",
    )
    sin_color["productos"][0]["ficha"].pop("color_primario")

    with pytest.raises(
        ErrorCatalogo,
        match=r"ficha\.color_primario",
    ):
        importar_catalogo(
            datos=sin_color,
            actor=actor,
        )


@pytest.mark.django_db(transaction=True)
def test_importador_piso_persiste_ficha_completa(django_user_model):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="import-piso-completo",
        )
    )

    datos = {
        "schema_version": 1,
        "productos": [
            {
                "sku": "PISO-IMPORT-1",
                "categoria": "PISO_FLOTANTE",
                "nombre": "Piso Roble Test",
                "precio_lista": "320.00",
                "stock_inicial": 6,
                "unidad_stock": "CAJA",
                "ficha": {
                    "marca": "MARCA_TEST",
                    "modelo": "Roble 8 mm",
                    "tipo": "LAMINADO",
                    "material": "HDF",
                    "diseno": "MADERA",
                    "espesor_mm": "8.00",
                    "acabado": "MATE",
                    "largo_mm": "1200.00",
                    "ancho_mm": "190.00",
                    "m2_por_caja": "2.2500",
                },
            }
        ],
    }

    resultado = importar_catalogo(
        datos=datos,
        actor=actor,
    )

    assert resultado.creados == 1
    assert resultado.movimientos_stock == 1

    producto = Producto.objects.get(
        sku="PISO-IMPORT-1",
    )
    ficha = ProductoPiso.objects.get(
        producto=producto,
    )

    assert producto.stock == 6
    assert producto.unidad_stock.codigo == "CAJA"

    assert ficha.marca.codigo == "MARCA_TEST"
    assert ficha.modelo == "Roble 8 mm"
    assert ficha.tipo.codigo == "LAMINADO"
    assert ficha.material.codigo == "HDF"
    assert ficha.diseno.codigo == "MADERA"
    assert str(ficha.espesor_mm) == "8.00"
    assert ficha.acabado.codigo == "MATE"
    assert str(ficha.largo_mm) == "1200.00"
    assert str(ficha.ancho_mm) == "190.00"
    assert str(ficha.m2_por_caja) == "2.2500"


@pytest.mark.django_db(transaction=True)
def test_importador_rechaza_campo_de_ficha_no_soportado(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="import-campo-desconocido",
        )
    )

    datos = catalogo()
    datos["productos"][0]["ficha"]["campo_inventado"] = "no permitido"

    with pytest.raises(
        ErrorCatalogo,
        match="campos de ficha no soportados",
    ):
        importar_catalogo(
            datos=datos,
            actor=actor,
        )

    assert not Producto.objects.filter(
        sku="IMPORT-1",
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_importador_repeticion_identica_es_idempotente(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="import-idempotencia-estricta",
        )
    )

    primera = importar_catalogo(
        datos=catalogo(),
        actor=actor,
    )

    segunda = importar_catalogo(
        datos=catalogo(),
        actor=actor,
    )

    producto = Producto.objects.get(
        sku="IMPORT-1",
    )

    assert primera.creados == 1
    assert primera.movimientos_stock == 1

    assert segunda.creados == 0
    assert segunda.existentes == 1
    assert segunda.movimientos_stock == 0

    assert producto.stock == 8
    assert (
        MovimientoStock.objects.filter(
            producto=producto,
            tipo_movimiento__concepto__codigo=("TIPO_MOVIMIENTO"),
            tipo_movimiento__codigo=("CARGA_INICIAL"),
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_importador_rechaza_mismo_sku_con_datos_distintos(
    django_user_model,
):
    actor = vendedor(
        django_user_model.objects.create_user(
            username="import-sku-incompatible",
        )
    )

    importar_catalogo(
        datos=catalogo(),
        actor=actor,
    )

    variantes = [
        catalogo(
            nombre="Nombre diferente",
        ),
        catalogo(
            precio_lista="1499.00",
        ),
        catalogo(
            stock_inicial=9,
        ),
        catalogo(
            ficha={
                "marca": "MARCA_TEST",
                "modelo": "Modelo diferente",
                "color_primario": "NEGRO",
                "color_secundario": "GRIS",
                "especificaciones": {
                    "respaldo": "malla",
                },
            },
        ),
    ]

    for datos in variantes:
        with pytest.raises(
            ErrorCatalogo,
            match="datos comerciales distintos",
        ):
            importar_catalogo(
                datos=datos,
                actor=actor,
            )

    producto = Producto.objects.get(
        sku="IMPORT-1",
    )

    assert producto.nombre == "Silla importada"
    assert str(producto.precio_lista) == "1500.00"
    assert producto.stock == 8
