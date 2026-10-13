from django.db import migrations


SQL = r'''-- Reglas aditivas: no reescribir migraciones publicadas de AP6.
-- Esta función protege la unidad efectiva que se descuenta; no convierte CAJA históricos.
CREATE OR REPLACE FUNCTION fn_validar_proforma_detalle()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_tipo TEXT; v_categoria TEXT; v_unidad TEXT; v_producto_activo BOOLEAN; v_unidad_stock TEXT;
BEGIN
    IF TG_OP='INSERT' OR NEW.tipo_item_id IS DISTINCT FROM OLD.tipo_item_id THEN
      IF NOT fn_catalogo_valor_pertenece_activo(NEW.tipo_item_id,'TIPO_ITEM') THEN
        RAISE EXCEPTION 'tipo_item_id inválido'; END IF;
    END IF;
    IF TG_OP='INSERT' OR NEW.unidad_id IS DISTINCT FROM OLD.unidad_id THEN
      IF NOT fn_catalogo_valor_pertenece_activo(NEW.unidad_id,'UNIDAD_MEDIDA') THEN
        RAISE EXCEPTION 'unidad_id inválida'; END IF;
    END IF;
    v_tipo := fn_catalogo_codigo_valor(NEW.tipo_item_id,'TIPO_ITEM');
    v_unidad := fn_catalogo_codigo_valor(NEW.unidad_id,'UNIDAD_MEDIDA');
    IF NEW.cantidad <= 0 THEN RAISE EXCEPTION 'cantidad debe ser positiva'; END IF;
    IF v_unidad IN ('PIEZA','JUEGO','BARRA','CAJA') AND NEW.cantidad <> TRUNC(NEW.cantidad) THEN
      RAISE EXCEPTION 'La unidad % requiere cantidad entera', v_unidad;
    END IF;
    IF v_tipo='MUEBLE_MEDIDA' THEN
      IF NEW.producto_id IS NOT NULL OR NEW.familia_producto_id IS NOT NULL THEN
        RAISE EXCEPTION 'MUEBLE_MEDIDA no apunta al catálogo'; END IF;
      IF v_unidad NOT IN ('PIEZA','JUEGO') THEN
        RAISE EXCEPTION 'MUEBLE_MEDIDA se cotiza en PIEZA o JUEGO'; END IF;
      RETURN NEW;
    END IF;
    IF NEW.producto_id IS NULL THEN
      IF NEW.familia_producto_id IS NULL THEN
        RAISE EXCEPTION 'Un ítem de catálogo requiere producto o familia pendiente'; END IF;
      IF NOT EXISTS (SELECT 1 FROM familias_producto f WHERE f.id=NEW.familia_producto_id AND f.activo) THEN
        RAISE EXCEPTION 'Familia pendiente inexistente o inactiva'; END IF;
      RETURN NEW;
    END IF;
    IF NEW.familia_producto_id IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM productos p WHERE p.id=NEW.producto_id AND p.familia_id=NEW.familia_producto_id
    ) THEN RAISE EXCEPTION 'El producto no pertenece a la familia indicada'; END IF;
    SELECT p.activo, fn_catalogo_codigo_valor(p.categoria_id,'CATEGORIA_PRODUCTO')
      INTO v_producto_activo,v_categoria FROM productos p WHERE p.id=NEW.producto_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Producto % no existe',NEW.producto_id; END IF;
    SELECT fn_catalogo_codigo_valor(p.unidad_stock_id,'UNIDAD_MEDIDA')
      INTO v_unidad_stock FROM productos p WHERE p.id=NEW.producto_id;
    IF v_unidad IS DISTINCT FROM v_unidad_stock THEN
      RAISE EXCEPTION 'Unidad de línea % incompatible con stock % del producto %',
        v_unidad,v_unidad_stock,NEW.producto_id;
    END IF;
    IF NOT v_producto_activo AND (TG_OP='INSERT' OR NEW.producto_id IS DISTINCT FROM OLD.producto_id) THEN
      RAISE EXCEPTION 'Producto % inactivo',NEW.producto_id; END IF;
    IF v_tipo='SILLA' AND (v_categoria<>'SILLA' OR v_unidad<>'PIEZA') THEN
      RAISE EXCEPTION 'SILLA requiere producto SILLA y PIEZA';
    ELSIF v_tipo='PISO_FLOTANTE' AND (v_categoria<>'PISO_FLOTANTE' OR v_unidad NOT IN ('M2','CAJA')) THEN
      RAISE EXCEPTION 'PISO_FLOTANTE requiere producto de piso y M2 (CAJA sólo histórica)';
    ELSIF v_tipo='OTRO' AND (v_categoria<>'OTRO' OR v_unidad NOT IN ('PIEZA','JUEGO','BARRA')) THEN
      RAISE EXCEPTION 'OTRO requiere PIEZA, JUEGO o BARRA';
    END IF;
    IF TG_OP='INSERT' AND v_tipo='PISO_FLOTANTE' AND v_unidad='CAJA' THEN
      RAISE EXCEPTION 'Una línea nueva de piso debe usar M2'; END IF;
    RETURN NEW;
END; $$;


CREATE OR REPLACE FUNCTION fn_calcular_total_detalle_proforma()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_bruto NUMERIC(20,4);
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
    IF NEW.descuento > ROUND(v_bruto, 2) THEN
        RAISE EXCEPTION 'El descuento no puede superar el importe bruto redondeado';
    END IF;
    NEW.total := ROUND(v_bruto, 2) - NEW.descuento;
    RETURN NEW;
END;
$$;

-- Cada subtotal equivale exactamente a la suma de los importes brutos
-- redondeados por línea. Equivalente: SUM(total + descuento).
-- Preserva el contexto de integridad de F07.2; no expone edición manual.
CREATE OR REPLACE FUNCTION fn_recalcular_totales_proforma(p_proforma_id BIGINT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE v_contexto_anterior TEXT;
BEGIN
    v_contexto_anterior := current_setting('homex.recalculo_proforma', TRUE);
    PERFORM set_config('homex.recalculo_proforma', '1', TRUE);
    UPDATE proformas
       SET subtotal = COALESCE((
               SELECT SUM(total + descuento) FROM proformas_detalle
               WHERE proforma_id = p_proforma_id
           ), 0),
           descuento_total = COALESCE((
               SELECT SUM(descuento) FROM proformas_detalle
               WHERE proforma_id = p_proforma_id
           ), 0),
           total = COALESCE((
               SELECT SUM(total) FROM proformas_detalle
               WHERE proforma_id = p_proforma_id
           ), 0)
     WHERE id=p_proforma_id;
    PERFORM set_config('homex.recalculo_proforma', COALESCE(v_contexto_anterior, ''), TRUE);
END;
$$;

-- Incluir 'total' impide manipulación directa en SQL sin campos de cálculo.
DROP TRIGGER IF EXISTS trg_calcular_total_detalle_proforma ON proformas_detalle;
CREATE TRIGGER trg_calcular_total_detalle_proforma
BEFORE INSERT OR UPDATE OF cantidad, precio_unitario, importe_negociado, modo_calculo, descuento, total
ON proformas_detalle FOR EACH ROW EXECUTE FUNCTION fn_calcular_total_detalle_proforma();
'''


class Migration(migrations.Migration):
    dependencies = [("proformas", "0006_ap6_reglas_comerciales")]
    operations = [migrations.RunSQL(SQL, reverse_sql=migrations.RunSQL.noop)]
