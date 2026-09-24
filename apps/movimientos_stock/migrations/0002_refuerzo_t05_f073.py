from django.db import migrations


FORWARD_SQL = """
CREATE OR REPLACE FUNCTION fn_reforzar_reversa_venta_t05()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_tipo TEXT;
    v_tipo_original TEXT;
    v_pedido_original BIGINT;
    v_estado_pedido_original TEXT;
BEGIN
    v_tipo := fn_catalogo_codigo_valor(
        NEW.tipo_movimiento_id,
        'TIPO_MOVIMIENTO'
    );

    -- Esta protección adicional sólo aplica a REVERSA_VENTA.
    IF v_tipo IS DISTINCT FROM 'REVERSA_VENTA' THEN
        RETURN NEW;
    END IF;

    IF NEW.movimiento_referencia_id IS NULL THEN
        RAISE EXCEPTION
            'REVERSA_VENTA requiere movimiento_referencia_id';
    END IF;

    /*
     * T05:
     * bloqueamos la VENTA original.
     *
     * Si dos transacciones intentan reversar la misma VENTA,
     * la segunda debe esperar a que termine la primera antes
     * de comprobar si ya existe una reversa.
     */
    SELECT
        fn_catalogo_codigo_valor(
            ms.tipo_movimiento_id,
            'TIPO_MOVIMIENTO'
        ),
        ms.pedido_id
    INTO
        v_tipo_original,
        v_pedido_original
    FROM movimientos_stock ms
    WHERE ms.id = NEW.movimiento_referencia_id
    FOR UPDATE;

    IF NOT FOUND
       OR v_tipo_original IS DISTINCT FROM 'VENTA' THEN
        RAISE EXCEPTION
            'REVERSA_VENTA debe referenciar una VENTA existente';
    END IF;

    IF v_pedido_original IS NULL THEN
        RAISE EXCEPTION
            'La VENTA original no tiene pedido asociado';
    END IF;

    SELECT fn_catalogo_codigo_valor(
        pe.estado_id,
        'ESTADO_PEDIDO'
    )
    INTO v_estado_pedido_original
    FROM pedidos pe
    WHERE pe.id = v_pedido_original;

    IF v_estado_pedido_original IS DISTINCT FROM 'CANCELADO' THEN
        RAISE EXCEPTION
            'REVERSA_VENTA sólo puede generarse al cancelar el pedido de la VENTA original';
    END IF;

    /*
     * La comprobación ocurre después de bloquear la VENTA.
     * Por tanto, una carrera concurrente no puede superar
     * simultáneamente este EXISTS.
     */
    IF EXISTS (
        SELECT 1
        FROM movimientos_stock r
        WHERE r.movimiento_referencia_id =
              NEW.movimiento_referencia_id
          AND fn_catalogo_valor_es(
                r.tipo_movimiento_id,
                'TIPO_MOVIMIENTO',
                'REVERSA_VENTA'
          )
    ) THEN
        RAISE EXCEPTION
            'La VENTA % ya fue reversada',
            NEW.movimiento_referencia_id;
    END IF;

    RETURN NEW;
END;
$$;


DROP TRIGGER IF EXISTS
    trg_00_reforzar_reversa_venta_t05
    ON movimientos_stock;

CREATE TRIGGER trg_00_reforzar_reversa_venta_t05
BEFORE INSERT ON movimientos_stock
FOR EACH ROW
EXECUTE FUNCTION fn_reforzar_reversa_venta_t05();
"""


REVERSE_SQL = """
DROP TRIGGER IF EXISTS
    trg_00_reforzar_reversa_venta_t05
    ON movimientos_stock;

DROP FUNCTION IF EXISTS
    fn_reforzar_reversa_venta_t05();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("movimientos_stock", "0001_initial"),
        ("capturas", "0004_cierre_integridad_f071_f072"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        )
    ]
