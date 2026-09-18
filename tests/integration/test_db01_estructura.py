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


@pytest.mark.django_db(transaction=True)
def test_defaults_fisicos_y_secuencia_de_proforma_funcionan_por_sql(django_user_model):
    from tests.factories import valor

    actor = django_user_model.objects.create_user(username="defaults-sql")
    estado = valor("ESTADO_PROFORMA", "BORRADOR")
    moneda = valor("MONEDA", "BOB")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO proformas (vendedor_id, estado_id, moneda_id)
            VALUES (%s, %s, %s) RETURNING numero, fecha
            """,
            [actor.id, estado.id, moneda.id],
        )
        primero = cursor.fetchone()
        cursor.execute(
            """
            INSERT INTO proformas (vendedor_id, estado_id, moneda_id)
            VALUES (%s, %s, %s) RETURNING numero, fecha
            """,
            [actor.id, estado.id, moneda.id],
        )
        segundo = cursor.fetchone()
        cursor.execute(
            """
            SELECT a.attname, pg_get_expr(ad.adbin, ad.adrelid)
            FROM pg_attrdef ad
            JOIN pg_attribute a ON a.attrelid = ad.adrelid AND a.attnum = ad.adnum
            WHERE ad.adrelid = 'proformas'::regclass
              AND a.attname IN ('numero', 'fecha')
            """
        )
        defaults = dict(cursor.fetchall())
    assert segundo[0] > primero[0]
    assert primero[1] is not None
    assert "nextval" in defaults["numero"]
    assert "CURRENT_DATE" in defaults["fecha"]


@pytest.mark.django_db
def test_constraints_criticos_y_fk_compuesta_existen():
    esperados = {
        "ck_productos_stock_nonnegative",
        "ck_detalle_cantidad_positive",
        "ck_recibo_pago_actual_positive",
        "ck_intento_intervalo",
        "ck_mov_stock_cantidad_nonzero",
        "fk_captura_detalle_misma_proforma",
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname FROM pg_constraint WHERE connamespace = 'public'::regnamespace"
        )
        constraints = {fila[0] for fila in cursor.fetchall()}
    assert esperados <= constraints


@pytest.mark.django_db
def test_funciones_y_triggers_v3_criticos_estan_instalados():
    funciones = {
        "fn_aprobar_proforma_crear_pedido",
        "fn_confirmar_pedido_descontar_stock",
        "fn_crear_orden_trabajo_pedido",
        "fn_actualizar_stock_desde_movimiento",
        "fn_cancelar_pedido_revertir_stock",
        "fn_crear_outbox_intento",
    }
    triggers = {
        "trg_aprobar_proforma_crear_pedido",
        "trg_pedido_01_descontar_stock",
        "trg_pedido_02_crear_orden_trabajo",
        "trg_actualizar_stock_desde_movimiento",
        "trg_crear_outbox_intento",
    }
    with connection.cursor() as cursor:
        cursor.execute("SELECT proname FROM pg_proc WHERE pronamespace = 'public'::regnamespace")
        presentes_funciones = {fila[0] for fila in cursor.fetchall()}
        cursor.execute("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
        presentes_triggers = {fila[0] for fila in cursor.fetchall()}
    assert funciones <= presentes_funciones
    assert triggers <= presentes_triggers


@pytest.mark.django_db
def test_defaults_fisicos_restantes_y_contratos_post_v3_existen():
    esperados = {
        ("catalogo_conceptos", "activo"),
        ("catalogo_valores", "activo"),
        ("clientes", "activo"),
        ("productos", "precio_lista"),
        ("productos", "stock"),
        ("productos", "activo"),
        ("productos_descuento", "activo"),
        ("proformas_detalle", "modo_calculo"),
        ("recibos", "estado"),
    }

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, a.attname, pg_get_expr(ad.adbin, ad.adrelid)
            FROM pg_attrdef ad
            JOIN pg_attribute a
              ON a.attrelid = ad.adrelid
             AND a.attnum = ad.adnum
            JOIN pg_class c ON c.oid = ad.adrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
            """
        )
        defaults = {(tabla, columna): expresion for tabla, columna, expresion in cursor.fetchall()}

    assert esperados <= defaults.keys()
    assert "PRECIO_UNITARIO" in defaults[("proformas_detalle", "modo_calculo")]
    assert "EMITIDO" in defaults[("recibos", "estado")]


@pytest.mark.django_db
def test_constraints_v3_restauran_semantica_completa():
    nombres = {
        "ck_detalle_snapshot_promocion",
        "ck_eval_counts",
        "ck_eval_precision_denominador",
    }

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT conname, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname = ANY(%s)
            """,
            [list(nombres)],
        )
        definiciones = dict(cursor.fetchall())

    assert nombres == definiciones.keys()
    assert "producto_id IS NOT NULL" in definiciones["ck_detalle_snapshot_promocion"]
    assert (
        "precio_ahora_snapshot < precio_antes_snapshot"
        in definiciones["ck_detalle_snapshot_promocion"]
    )
    assert "campos_corregidos <= campos_totales" in definiciones["ck_eval_counts"]
    assert "campos_totales > 0" in definiciones["ck_eval_precision_denominador"]
