from django.db import migrations


FORWARD_SQL = """
CREATE OR REPLACE FUNCTION fn_preparar_recibo()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_total_pedido NUMERIC(14,2);
    v_pagado_previo NUMERIC(14,2);
    v_estado_pedido TEXT;
BEGIN
    /*
     * T06 — un recibo emitido es evidencia comercial inmutable.
     *
     * En UPDATE sólo se admite:
     *
     *     EMITIDO -> ANULADO
     *
     * Se permite actualizar updated_by como metadato de auditoría.
     * Ningún dato comercial puede cambiar durante la anulación.
     */
    IF TG_OP = 'UPDATE' THEN
        IF OLD.estado IS DISTINCT FROM 'EMITIDO'
           OR NEW.estado IS DISTINCT FROM 'ANULADO' THEN
            RAISE EXCEPTION
                'Un recibo sólo admite la transición EMITIDO -> ANULADO';
        END IF;

        IF NEW.numero IS DISTINCT FROM OLD.numero
           OR NEW.pedido_id IS DISTINCT FROM OLD.pedido_id
           OR NEW.nombre_completo IS DISTINCT FROM OLD.nombre_completo
           OR NEW.monto_en_letras IS DISTINCT FROM OLD.monto_en_letras
           OR NEW.concepto IS DISTINCT FROM OLD.concepto
           OR NEW.tipo_pago_id IS DISTINCT FROM OLD.tipo_pago_id
           OR NEW.numero_cheque IS DISTINCT FROM OLD.numero_cheque
           OR NEW.banco IS DISTINCT FROM OLD.banco
           OR NEW.total IS DISTINCT FROM OLD.total
           OR NEW.pago_actual IS DISTINCT FROM OLD.pago_actual
           OR NEW.a_cuenta IS DISTINCT FROM OLD.a_cuenta
           OR NEW.saldo IS DISTINCT FROM OLD.saldo
           OR NEW.fecha IS DISTINCT FROM OLD.fecha
           OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id THEN
            RAISE EXCEPTION
                'La anulación no puede modificar datos comerciales del recibo';
        END IF;

        /*
         * Cobro, anulación y cancelación deben serializarse sobre
         * la misma fila Pedido.
         */
        PERFORM 1
        FROM pedidos pe
        WHERE pe.id = OLD.pedido_id
        FOR UPDATE;

        IF NOT FOUND THEN
            RAISE EXCEPTION
                'Pedido % no existe',
                OLD.pedido_id;
        END IF;

        RETURN NEW;
    END IF;

    /*
     * Todo recibo nuevo nace EMITIDO.
     */
    IF NEW.estado IS DISTINCT FROM 'EMITIDO' THEN
        RAISE EXCEPTION
            'Un recibo nuevo debe emitirse en estado EMITIDO';
    END IF;

    /*
     * Se preservan las validaciones existentes antes de F07.4:
     * tipo de pago válido y reglas específicas para CHEQUE.
     */
    IF NOT fn_catalogo_valor_pertenece_activo(
        NEW.tipo_pago_id,
        'TIPO_PAGO'
    ) THEN
        RAISE EXCEPTION
            'tipo_pago_id % no pertenece a TIPO_PAGO activo',
            NEW.tipo_pago_id;
    END IF;

    IF fn_catalogo_valor_es(
        NEW.tipo_pago_id,
        'TIPO_PAGO',
        'CHEQUE'
    ) THEN
        IF NULLIF(BTRIM(NEW.numero_cheque), '') IS NULL THEN
            RAISE EXCEPTION
                'Un recibo CHEQUE requiere numero_cheque';
        END IF;

        IF NULLIF(BTRIM(NEW.banco), '') IS NULL THEN
            RAISE EXCEPTION
                'Un recibo CHEQUE requiere banco';
        END IF;
    ELSE
        NEW.numero_cheque := NULL;
        NEW.banco := NULL;
    END IF;

    /*
     * P27:
     * el cobro sólo puede emitirse sobre un Pedido CONFIRMADO.
     *
     * El SELECT FOR UPDATE serializa también cobros concurrentes,
     * anulaciones y cancelaciones.
     */
    SELECT fn_catalogo_codigo_valor(
        pe.estado_id,
        'ESTADO_PEDIDO'
    )
    INTO v_estado_pedido
    FROM pedidos pe
    WHERE pe.id = NEW.pedido_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Pedido % no existe',
            NEW.pedido_id;
    END IF;

    IF v_estado_pedido IS DISTINCT FROM 'CONFIRMADO' THEN
        RAISE EXCEPTION
            'Los cobros sólo pueden registrarse sobre un pedido CONFIRMADO';
    END IF;

    SELECT p.total
    INTO v_total_pedido
    FROM pedidos pe
    JOIN proformas p
      ON p.id = pe.proforma_id
    WHERE pe.id = NEW.pedido_id;

    /*
     * G03:
     * únicamente los recibos EMITIDOS forman parte del acumulado.
     */
    SELECT COALESCE(
        SUM(r.pago_actual),
        0
    )
    INTO v_pagado_previo
    FROM recibos r
    WHERE r.pedido_id = NEW.pedido_id
      AND r.estado = 'EMITIDO';

    IF v_pagado_previo + NEW.pago_actual > v_total_pedido THEN
        RAISE EXCEPTION
            'El pago excede el total del pedido. Total: %, pagado: %, nuevo pago: %',
            v_total_pedido,
            v_pagado_previo,
            NEW.pago_actual;
    END IF;

    NEW.total := v_total_pedido;
    NEW.a_cuenta := v_pagado_previo + NEW.pago_actual;
    NEW.saldo := v_total_pedido - NEW.a_cuenta;

    RETURN NEW;
END;
$$;
"""


REVERSE_SQL = """
CREATE OR REPLACE FUNCTION fn_preparar_recibo()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_total NUMERIC(14,2);
    v_pagado NUMERIC(14,2);
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF OLD.estado = 'ANULADO'
           OR NEW.estado NOT IN ('EMITIDO','ANULADO')
           OR (
               OLD.estado = 'EMITIDO'
               AND NEW.estado = 'EMITIDO'
               AND NEW IS DISTINCT FROM OLD
           ) THEN
            RAISE EXCEPTION
                'Un recibo emitido sólo puede anularse; no admite edición comercial';
        END IF;

        IF OLD.estado = 'EMITIDO'
           AND NEW.estado = 'ANULADO' THEN
            RETURN NEW;
        END IF;
    END IF;

    IF NEW.estado <> 'EMITIDO' THEN
        RAISE EXCEPTION
            'Un recibo nuevo debe emitirse';
    END IF;

    PERFORM 1
    FROM pedidos
    WHERE id = NEW.pedido_id
    FOR UPDATE;

    IF NOT FOUND
       OR EXISTS (
           SELECT 1
           FROM pedidos p
           JOIN catalogo_valores e
             ON e.id = p.estado_id
           WHERE p.id = NEW.pedido_id
             AND e.codigo = 'CANCELADO'
       ) THEN
        RAISE EXCEPTION
            'No se cobra un pedido cancelado o inexistente';
    END IF;

    SELECT p.total
    INTO v_total
    FROM pedidos pe
    JOIN proformas p
      ON p.id = pe.proforma_id
    WHERE pe.id = NEW.pedido_id;

    SELECT COALESCE(
        SUM(pago_actual),
        0
    )
    INTO v_pagado
    FROM recibos
    WHERE pedido_id = NEW.pedido_id
      AND estado = 'EMITIDO'
      AND (
          TG_OP = 'INSERT'
          OR id <> OLD.id
      );

    IF v_pagado + NEW.pago_actual > v_total THEN
        RAISE EXCEPTION
            'El pago excede el total';
    END IF;

    NEW.total := v_total;
    NEW.a_cuenta := v_pagado + NEW.pago_actual;
    NEW.saldo := v_total - NEW.a_cuenta;

    RETURN NEW;
END;
$$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("recibos", "0002_reglas_f074"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        )
    ]
