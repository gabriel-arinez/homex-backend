import pytest
from django.db import DatabaseError, connection

from apps.catalogo.models import ConceptoCatalogo

TABLAS_COMERCIALES = {
    "catalogo_conceptos",
    "catalogo_valores",
    "clientes",
    "productos",
    "productos_silla",
    "productos_piso",
    "productos_descuento",
    "proformas",
    "proformas_detalle",
    "especificaciones_mueble",
    "pedidos",
    "transiciones_estado_pedido",
    "ordenes_trabajo",
    "notas_entrega",
    "recibos",
    "archivos_adjuntos",
    "capturas",
    "intentos_captura",
    "trabajos_outbox",
    "items_ia",
    "items_humano",
    "evaluaciones_nlp",
    "mediciones_proceso",
    "movimientos_stock",
}
SECUENCIAS = {
    "seq_proformas_numero",
    "seq_ordenes_trabajo_numero",
    "seq_notas_entrega_numero",
    "seq_recibos_numero",
}


@pytest.mark.django_db
def test_db01_crea_las_24_tablas_y_cuatro_secuencias():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        tablas = {row[0] for row in cursor.fetchall()}
        cursor.execute(
            (
                "SELECT sequence_name FROM information_schema.sequences "
                "WHERE sequence_schema = 'public'"
            )
        )
        secuencias = {row[0] for row in cursor.fetchall()}
    assert TABLAS_COMERCIALES <= tablas
    assert SECUENCIAS <= secuencias


@pytest.mark.django_db(transaction=True)
def test_catalogo_estructura_es_inmutable_en_postgresql():
    concepto = ConceptoCatalogo.objects.create(codigo="PRUEBA_ESTRUCTURAL")
    concepto.codigo = "NO_PERMITIDO"
    with pytest.raises(DatabaseError):
        concepto.save(update_fields=["codigo"])


@pytest.mark.django_db
def test_campos_tecnicos_conservan_el_contrato_fisico():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'proformas'"
        )
        proforma = {row[0] for row in cursor.fetchall()}
        cursor.execute(
            (
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'evaluaciones_nlp'"
            )
        )
        evaluacion = {row[0] for row in cursor.fetchall()}
    assert {"created_by_id", "updated_by_id"} <= proforma
    assert "evaluated_by_id" in evaluacion
    assert "creado_por_id" not in proforma
    assert "evaluado_por_id" not in evaluacion


@pytest.mark.django_db
def test_claves_foraneas_de_auditoria_apuntan_al_usuario_configurado():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.conrelid::regclass::text, a.attname, confrelid::regclass::text
            FROM pg_constraint AS c
            JOIN unnest(c.conkey) AS key(attnum) ON TRUE
            JOIN pg_attribute AS a
              ON a.attrelid = c.conrelid AND a.attnum = key.attnum
            WHERE c.contype = 'f'
              AND c.conrelid::regclass::text IN ('proformas', 'evaluaciones_nlp')
              AND a.attname IN ('created_by_id', 'updated_by_id', 'evaluated_by_id')
            """
        )
        referencias = set(cursor.fetchall())

    assert {
        ("proformas", "created_by_id", "accounts_user"),
        ("proformas", "updated_by_id", "accounts_user"),
        ("evaluaciones_nlp", "evaluated_by_id", "accounts_user"),
    } <= referencias
