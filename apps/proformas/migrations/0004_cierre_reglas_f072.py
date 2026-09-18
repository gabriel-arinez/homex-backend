from django.db import migrations


FORWARD_SQL = """
CREATE OR REPLACE FUNCTION fn_recalcular_totales_proforma(p_proforma_id BIGINT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_contexto_anterior TEXT;
BEGIN
    v_contexto_anterior := current_setting('homex.recalculo_proforma', TRUE);
    PERFORM set_config('homex.recalculo_proforma', '1', TRUE);

    UPDATE proformas
    SET subtotal = COALESCE((
            SELECT SUM(
                CASE
                    WHEN modo_calculo = 'TOTAL_NEGOCIADO' THEN importe_negociado
                    ELSE cantidad * precio_unitario
                END
            )
            FROM proformas_detalle
            WHERE proforma_id = p_proforma_id
        ), 0),
        descuento_total = COALESCE((
            SELECT SUM(descuento)
            FROM proformas_detalle
            WHERE proforma_id = p_proforma_id
        ), 0),
        total = COALESCE((
            SELECT SUM(total)
            FROM proformas_detalle
            WHERE proforma_id = p_proforma_id
        ), 0)
    WHERE id = p_proforma_id;

    PERFORM set_config(
        'homex.recalculo_proforma',
        COALESCE(v_contexto_anterior, ''),
        TRUE
    );
END;
$$;

CREATE OR REPLACE FUNCTION fn_preparar_proforma_para_emision()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_nuevo_estado TEXT;
    v_faltantes INTEGER;
    v_cliente clientes%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE'
       AND NOT fn_catalogo_valor_es(OLD.estado_id, 'ESTADO_PROFORMA', 'BORRADOR')
       AND (
            NEW.cliente_id IS DISTINCT FROM OLD.cliente_id
            OR NEW.cliente_nombre_snapshot IS DISTINCT FROM OLD.cliente_nombre_snapshot
            OR NEW.cliente_empresa_snapshot IS DISTINCT FROM OLD.cliente_empresa_snapshot
            OR NEW.cliente_celular_snapshot IS DISTINCT FROM OLD.cliente_celular_snapshot
            OR NEW.cliente_direccion_snapshot IS DISTINCT FROM OLD.cliente_direccion_snapshot
       ) THEN
        RAISE EXCEPTION 'Cliente y snapshots quedan congelados desde ENVIADA';
    END IF;

    v_nuevo_estado := fn_catalogo_codigo_valor(NEW.estado_id, 'ESTADO_PROFORMA');

    IF TG_OP = 'UPDATE' AND NEW.estado_id IS NOT DISTINCT FROM OLD.estado_id THEN
        RETURN NEW;
    END IF;

    IF v_nuevo_estado IN ('ENVIADA', 'APROBADA') THEN
        IF NEW.cliente_id IS NULL THEN
            RAISE EXCEPTION 'Una proforma emitida requiere cliente';
        END IF;

        SELECT *
        INTO v_cliente
        FROM clientes
        WHERE id = NEW.cliente_id
          AND activo = TRUE;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'El cliente no existe o está inactivo';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM proformas_detalle
            WHERE proforma_id = NEW.id
        ) THEN
            RAISE EXCEPTION 'La proforma requiere al menos un detalle';
        END IF;

        IF NEW.total <= 0 THEN
            RAISE EXCEPTION 'La proforma requiere total positivo';
        END IF;

        SELECT COUNT(*)
        INTO v_faltantes
        FROM proformas_detalle pd
        WHERE pd.proforma_id = NEW.id
          AND fn_catalogo_valor_es(pd.tipo_item_id, 'TIPO_ITEM', 'MUEBLE_MEDIDA')
          AND NOT EXISTS (
              SELECT 1
              FROM especificaciones_mueble em
              WHERE em.proforma_detalle_id = pd.id
          );

        IF v_faltantes > 0 THEN
            RAISE EXCEPTION 'Hay muebles a medida sin especificación';
        END IF;

        IF NEW.cliente_nombre_snapshot IS NULL THEN
            NEW.cliente_nombre_snapshot := NULLIF(
                BTRIM(CONCAT_WS(' ', v_cliente.nombres, v_cliente.apellidos)),
                ''
            );
            NEW.cliente_empresa_snapshot := v_cliente.empresa;
            NEW.cliente_celular_snapshot := v_cliente.celular;
            NEW.cliente_direccion_snapshot := v_cliente.direccion;
        END IF;
    ELSIF v_nuevo_estado <> 'BORRADOR' AND NEW.cliente_id IS NULL THEN
        RAISE EXCEPTION 'cliente_id sólo puede ser NULL mientras la proforma está en BORRADOR';
    END IF;

    RETURN NEW;
END;
$$;
"""


REVERSE_SQL = """
CREATE OR REPLACE FUNCTION fn_recalcular_totales_proforma(p_proforma_id BIGINT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM set_config('homex.recalculo_proforma', '1', TRUE);
    UPDATE proformas
    SET subtotal = COALESCE((
            SELECT SUM(CASE WHEN modo_calculo = 'TOTAL_NEGOCIADO'
                            THEN importe_negociado
                            ELSE cantidad * precio_unitario END)
            FROM proformas_detalle WHERE proforma_id = p_proforma_id
        ), 0),
        descuento_total = COALESCE((
            SELECT SUM(descuento) FROM proformas_detalle WHERE proforma_id = p_proforma_id
        ), 0),
        total = COALESCE((
            SELECT SUM(total) FROM proformas_detalle WHERE proforma_id = p_proforma_id
        ), 0)
    WHERE id = p_proforma_id;
END;
$$;

CREATE OR REPLACE FUNCTION fn_preparar_proforma_para_emision()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_nuevo_estado TEXT;
    v_faltantes INTEGER;
    v_cliente clientes%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE'
       AND NOT fn_catalogo_valor_es(OLD.estado_id, 'ESTADO_PROFORMA', 'BORRADOR')
       AND (NEW.cliente_id IS DISTINCT FROM OLD.cliente_id
            OR NEW.cliente_nombre_snapshot IS DISTINCT FROM OLD.cliente_nombre_snapshot
            OR NEW.cliente_empresa_snapshot IS DISTINCT FROM OLD.cliente_empresa_snapshot
            OR NEW.cliente_celular_snapshot IS DISTINCT FROM OLD.cliente_celular_snapshot
            OR NEW.cliente_direccion_snapshot IS DISTINCT FROM OLD.cliente_direccion_snapshot) THEN
        RAISE EXCEPTION 'Cliente y snapshots quedan congelados desde ENVIADA';
    END IF;
    v_nuevo_estado := fn_catalogo_codigo_valor(NEW.estado_id, 'ESTADO_PROFORMA');
    IF v_nuevo_estado IN ('ENVIADA', 'APROBADA') THEN
        IF NEW.cliente_id IS NULL THEN RAISE EXCEPTION 'Una proforma emitida requiere cliente'; END IF;
        SELECT * INTO v_cliente FROM clientes WHERE id = NEW.cliente_id AND activo = TRUE;
        IF NOT FOUND THEN RAISE EXCEPTION 'El cliente no existe o está inactivo'; END IF;
        IF NOT EXISTS (SELECT 1 FROM proformas_detalle WHERE proforma_id = NEW.id) THEN
            RAISE EXCEPTION 'La proforma requiere al menos un detalle';
        END IF;
        IF NEW.total <= 0 THEN RAISE EXCEPTION 'La proforma requiere total positivo'; END IF;
        SELECT COUNT(*) INTO v_faltantes FROM proformas_detalle pd
        WHERE pd.proforma_id = NEW.id
          AND fn_catalogo_valor_es(pd.tipo_item_id, 'TIPO_ITEM', 'MUEBLE_MEDIDA')
          AND NOT EXISTS (SELECT 1 FROM especificaciones_mueble em WHERE em.proforma_detalle_id = pd.id);
        IF v_faltantes > 0 THEN RAISE EXCEPTION 'Hay muebles a medida sin especificación'; END IF;
        IF NEW.cliente_nombre_snapshot IS NULL THEN
            NEW.cliente_nombre_snapshot := NULLIF(BTRIM(CONCAT_WS(' ', v_cliente.nombres, v_cliente.apellidos)), '');
            NEW.cliente_empresa_snapshot := v_cliente.empresa;
            NEW.cliente_celular_snapshot := v_cliente.celular;
            NEW.cliente_direccion_snapshot := v_cliente.direccion;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("proformas", "0003_reglas_comerciales_f072"),
        ("capturas", "0003_refuerzo_estructural_f071_f072"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        )
    ]
