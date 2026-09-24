from django.db import migrations

FORWARD_SQL = """
CREATE OR REPLACE FUNCTION fn_proteger_carga_inicial_unica_f075()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_tipo TEXT;
BEGIN
    v_tipo := fn_catalogo_codigo_valor(
        NEW.tipo_movimiento_id,
        'TIPO_MOVIMIENTO'
    );

    IF v_tipo IS DISTINCT FROM 'CARGA_INICIAL' THEN
        RETURN NEW;
    END IF;

    /*
     * Serializa intentos concurrentes sobre el mismo producto.
     *
     * Dos transacciones que intenten registrar CARGA_INICIAL al mismo tiempo
     * no pueden superar simultáneamente la comprobación posterior.
     */
    PERFORM 1
    FROM productos
    WHERE id = NEW.producto_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Producto % no existe',
            NEW.producto_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM movimientos_stock ms
        WHERE ms.producto_id = NEW.producto_id
          AND fn_catalogo_valor_es(
                ms.tipo_movimiento_id,
                'TIPO_MOVIMIENTO',
                'CARGA_INICIAL'
          )
    ) THEN
        RAISE EXCEPTION
            'El producto % ya tiene una CARGA_INICIAL registrada',
            NEW.producto_id;
    END IF;

    RETURN NEW;
END;
$$;


DROP TRIGGER IF EXISTS
    trg_00_proteger_carga_inicial_unica_f075
    ON movimientos_stock;

CREATE TRIGGER trg_00_proteger_carga_inicial_unica_f075
BEFORE INSERT ON movimientos_stock
FOR EACH ROW
EXECUTE FUNCTION fn_proteger_carga_inicial_unica_f075();
"""


REVERSE_SQL = """
DROP TRIGGER IF EXISTS
    trg_00_proteger_carga_inicial_unica_f075
    ON movimientos_stock;

DROP FUNCTION IF EXISTS
    fn_proteger_carga_inicial_unica_f075();
"""


class Migration(migrations.Migration):
    dependencies = [
        (
            "movimientos_stock",
            "0002_refuerzo_t05_f073",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]
