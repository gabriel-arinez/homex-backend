from django.db import migrations


SQL = r'''
-- Preservar operaciones por movimiento de existencias CAJA heredadas.
-- No se permite insertar nuevos pisos CAJA ni reconvertir registros existentes.
CREATE OR REPLACE FUNCTION fn_validar_producto_catalogos()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_categoria TEXT; v_unidad TEXT;
BEGIN
    IF NOT fn_catalogo_valor_pertenece_activo(NEW.categoria_id, 'CATEGORIA_PRODUCTO') THEN
        RAISE EXCEPTION 'categoria_id % no pertenece a CATEGORIA_PRODUCTO activo', NEW.categoria_id;
    END IF;
    IF NOT fn_catalogo_valor_pertenece_activo(NEW.unidad_stock_id, 'UNIDAD_MEDIDA') THEN
        RAISE EXCEPTION 'unidad_stock_id % no pertenece a UNIDAD_MEDIDA activa', NEW.unidad_stock_id;
    END IF;
    v_categoria := fn_catalogo_codigo_valor(NEW.categoria_id, 'CATEGORIA_PRODUCTO');
    v_unidad := fn_catalogo_codigo_valor(NEW.unidad_stock_id, 'UNIDAD_MEDIDA');
    IF v_categoria = 'PISO_FLOTANTE' AND v_unidad <> 'M2' THEN
        -- Una unidad CAJA ya existente sólo puede permanecer sin alterarse.
        -- UPDATE de stock/movimientos o metadatos debe continuar disponible.
        IF TG_OP = 'INSERT' THEN
            RAISE EXCEPTION 'Un PISO_FLOTANTE nuevo debe manejar stock en M2';
        END IF;
        IF v_unidad <> 'CAJA'
           OR NEW.unidad_stock_id IS DISTINCT FROM OLD.unidad_stock_id
           OR NEW.categoria_id IS DISTINCT FROM OLD.categoria_id THEN
            RAISE EXCEPTION 'No se admite convertir ni cambiar una unidad histórica CAJA';
        END IF;
    ELSIF v_categoria = 'SILLA' AND v_unidad <> 'PIEZA' THEN
        RAISE EXCEPTION 'Una SILLA debe manejar stock en PIEZA';
    ELSIF v_categoria = 'OTRO' AND v_unidad NOT IN ('PIEZA','JUEGO','BARRA') THEN
        RAISE EXCEPTION 'Un producto OTRO debe usar PIEZA, JUEGO o BARRA';
    END IF;
    RETURN NEW;
END; $$;


'''


class Migration(migrations.Migration):
    dependencies = [("proformas", "0007_ap6_unidades_redondeo")]
    operations = [migrations.RunSQL(SQL, reverse_sql=migrations.RunSQL.noop)]
