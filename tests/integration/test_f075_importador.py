import pytest

from apps.catalogo.importador import ErrorCatalogo, importar_catalogo
from apps.catalogo.models import Producto
from tests.factories import vendedor


def catalogo(sku="IMPORT-1", **cambios):
    producto = {
        "sku": sku,
        "categoria": "SILLA",
        "nombre": "Silla importada",
        "precio_lista": "1500.00",
        "stock_inicial": 8,
        "unidad_stock": "PIEZA",
        "ficha": {"modelo": "B15", "especificaciones": {"respaldo": "malla"}},
    }
    producto.update(cambios)
    return {"schema_version": 1, "productos": [producto]}


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
