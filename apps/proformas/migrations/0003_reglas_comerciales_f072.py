from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("proformas", "0002_detalleproforma_ck_detalle_modo_calculo_and_more")]

    operations = [
        migrations.RunSQL(
            sql="""
CREATE OR REPLACE FUNCTION fn_validar_descuento_producto()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.precio_ahora > NEW.precio_antes THEN
        RAISE EXCEPTION 'precio_ahora no puede superar precio_antes';
    END IF;
    IF NEW.fecha_inicio IS NOT NULL AND NEW.fecha_fin IS NOT NULL
       AND NEW.fecha_fin < NEW.fecha_inicio THEN
        RAISE EXCEPTION 'fecha_fin no puede preceder fecha_inicio';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_validar_descuento_producto ON productos_descuento;
CREATE TRIGGER trg_validar_descuento_producto
BEFORE INSERT OR UPDATE ON productos_descuento
FOR EACH ROW EXECUTE FUNCTION fn_validar_descuento_producto();

CREATE OR REPLACE FUNCTION fn_calcular_total_detalle_proforma()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_bruto NUMERIC(14,2);
BEGIN
    IF NEW.cantidad <= 0 OR NEW.descuento < 0 THEN
        RAISE EXCEPTION 'cantidad debe ser positiva y descuento no negativo';
    END IF;
    IF NEW.modo_calculo = 'PRECIO_UNITARIO' THEN
        IF NEW.importe_negociado IS NOT NULL OR NEW.precio_unitario < 0 THEN
            RAISE EXCEPTION 'PRECIO_UNITARIO requiere precio no negativo e importe_negociado NULL';
        END IF;
        v_bruto := NEW.cantidad * NEW.precio_unitario;
    ELSIF NEW.modo_calculo = 'TOTAL_NEGOCIADO' THEN
        IF NEW.importe_negociado IS NULL OR NEW.importe_negociado < 0 THEN
            RAISE EXCEPTION 'TOTAL_NEGOCIADO requiere importe_negociado no negativo';
        END IF;
        v_bruto := NEW.importe_negociado;
    ELSE
        RAISE EXCEPTION 'modo_calculo inválido: %', NEW.modo_calculo;
    END IF;
    IF NEW.descuento > v_bruto THEN
        RAISE EXCEPTION 'El descuento no puede superar el importe bruto';
    END IF;
    NEW.total := v_bruto - NEW.descuento;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_calcular_total_detalle_proforma ON proformas_detalle;
CREATE TRIGGER trg_calcular_total_detalle_proforma
BEFORE INSERT OR UPDATE OF cantidad, precio_unitario, importe_negociado, modo_calculo, descuento
ON proformas_detalle FOR EACH ROW EXECUTE FUNCTION fn_calcular_total_detalle_proforma();

CREATE OR REPLACE FUNCTION fn_proteger_proforma_detalle_proforma()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.proforma_id IS DISTINCT FROM OLD.proforma_id THEN
        RAISE EXCEPTION 'proformas_detalle.proforma_id es inmutable';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_proteger_proforma_detalle_proforma ON proformas_detalle;
CREATE TRIGGER trg_proteger_proforma_detalle_proforma
BEFORE UPDATE OF proforma_id ON proformas_detalle
FOR EACH ROW EXECUTE FUNCTION fn_proteger_proforma_detalle_proforma();

CREATE OR REPLACE FUNCTION fn_recalcular_totales_proforma(p_proforma_id BIGINT)
RETURNS VOID LANGUAGE plpgsql AS $$
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

CREATE OR REPLACE FUNCTION fn_proteger_totales_proforma()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.subtotal, NEW.descuento_total, NEW.total)
       IS DISTINCT FROM (OLD.subtotal, OLD.descuento_total, OLD.total)
       AND COALESCE(current_setting('homex.recalculo_proforma', TRUE), '') <> '1' THEN
        RAISE EXCEPTION 'Los totales de proforma son calculados por PostgreSQL';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_proteger_totales_proforma ON proformas;
CREATE TRIGGER trg_proteger_totales_proforma
BEFORE UPDATE OF subtotal, descuento_total, total ON proformas
FOR EACH ROW EXECUTE FUNCTION fn_proteger_totales_proforma();

CREATE OR REPLACE FUNCTION fn_preparar_proforma_para_emision()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
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

DROP TRIGGER IF EXISTS trg_preparar_proforma_para_emision ON proformas;
CREATE TRIGGER trg_preparar_proforma_para_emision
BEFORE INSERT OR UPDATE ON proformas
FOR EACH ROW EXECUTE FUNCTION fn_preparar_proforma_para_emision();

CREATE OR REPLACE FUNCTION fn_bloquear_especificacion_aprobada()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_detalle_id BIGINT; v_estado_id BIGINT;
BEGIN
    v_detalle_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.proforma_detalle_id ELSE NEW.proforma_detalle_id END;
    SELECT p.estado_id INTO v_estado_id FROM proformas_detalle pd JOIN proformas p ON p.id = pd.proforma_id WHERE pd.id = v_detalle_id;
    IF fn_catalogo_valor_es(v_estado_id, 'ESTADO_PROFORMA', 'APROBADA') THEN
        RAISE EXCEPTION 'No se puede modificar una especificación de proforma APROBADA';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;
DROP TRIGGER IF EXISTS trg_bloquear_especificacion_aprobada ON especificaciones_mueble;
CREATE TRIGGER trg_bloquear_especificacion_aprobada
BEFORE UPDATE OR DELETE ON especificaciones_mueble
FOR EACH ROW EXECUTE FUNCTION fn_bloquear_especificacion_aprobada();
""",
            reverse_sql=migrations.RunSQL.noop,
        )
    ]
