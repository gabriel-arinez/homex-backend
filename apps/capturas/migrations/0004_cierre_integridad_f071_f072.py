from django.db import migrations


FORWARD_SQL = """
ALTER TABLE catalogo_conceptos ALTER COLUMN activo SET DEFAULT TRUE;
ALTER TABLE catalogo_valores ALTER COLUMN activo SET DEFAULT TRUE;
ALTER TABLE clientes ALTER COLUMN activo SET DEFAULT TRUE;
ALTER TABLE productos ALTER COLUMN precio_lista SET DEFAULT 0;
ALTER TABLE productos ALTER COLUMN stock SET DEFAULT 0;
ALTER TABLE productos ALTER COLUMN activo SET DEFAULT TRUE;
ALTER TABLE productos_descuento ALTER COLUMN activo SET DEFAULT TRUE;

ALTER TABLE proformas_detalle ALTER COLUMN modo_calculo SET DEFAULT 'PRECIO_UNITARIO';
ALTER TABLE recibos ALTER COLUMN estado SET DEFAULT 'EMITIDO';

ALTER TABLE proformas_detalle
    DROP CONSTRAINT IF EXISTS ck_detalle_snapshot_promocion;
ALTER TABLE proformas_detalle
    ADD CONSTRAINT ck_detalle_snapshot_promocion CHECK (
        (precio_antes_snapshot IS NULL AND precio_ahora_snapshot IS NULL)
        OR
        (
            producto_id IS NOT NULL
            AND precio_antes_snapshot IS NOT NULL
            AND precio_ahora_snapshot IS NOT NULL
            AND precio_antes_snapshot >= 0
            AND precio_ahora_snapshot >= 0
            AND precio_ahora_snapshot < precio_antes_snapshot
        )
    );

ALTER TABLE evaluaciones_nlp
    DROP CONSTRAINT IF EXISTS ck_eval_counts;
ALTER TABLE evaluaciones_nlp
    ADD CONSTRAINT ck_eval_counts CHECK (
        campos_totales >= 0
        AND campos_corregidos >= 0
        AND campos_agregados >= 0
        AND campos_eliminados >= 0
        AND campos_corregidos <= campos_totales
    );

ALTER TABLE evaluaciones_nlp
    ADD CONSTRAINT ck_eval_precision_denominador CHECK (
        campos_totales > 0 OR precision_campo IS NULL
    );
"""


REVERSE_SQL = """
ALTER TABLE evaluaciones_nlp
    DROP CONSTRAINT IF EXISTS ck_eval_precision_denominador;

ALTER TABLE evaluaciones_nlp
    DROP CONSTRAINT IF EXISTS ck_eval_counts;
ALTER TABLE evaluaciones_nlp
    ADD CONSTRAINT ck_eval_counts CHECK (
        campos_totales >= 0
        AND campos_corregidos >= 0
        AND campos_agregados >= 0
        AND campos_eliminados >= 0
    );

ALTER TABLE proformas_detalle
    DROP CONSTRAINT IF EXISTS ck_detalle_snapshot_promocion;
ALTER TABLE proformas_detalle
    ADD CONSTRAINT ck_detalle_snapshot_promocion CHECK (
        (precio_antes_snapshot IS NULL AND precio_ahora_snapshot IS NULL)
        OR
        (precio_antes_snapshot IS NOT NULL AND precio_ahora_snapshot IS NOT NULL)
    );

ALTER TABLE catalogo_conceptos ALTER COLUMN activo DROP DEFAULT;
ALTER TABLE catalogo_valores ALTER COLUMN activo DROP DEFAULT;
ALTER TABLE clientes ALTER COLUMN activo DROP DEFAULT;
ALTER TABLE productos ALTER COLUMN precio_lista DROP DEFAULT;
ALTER TABLE productos ALTER COLUMN stock DROP DEFAULT;
ALTER TABLE productos ALTER COLUMN activo DROP DEFAULT;
ALTER TABLE productos_descuento ALTER COLUMN activo DROP DEFAULT;
ALTER TABLE proformas_detalle ALTER COLUMN modo_calculo DROP DEFAULT;
ALTER TABLE recibos ALTER COLUMN estado DROP DEFAULT;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("capturas", "0003_refuerzo_estructural_f071_f072"),
        ("proformas", "0004_cierre_reglas_f072"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        )
    ]
