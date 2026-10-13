from django.db import migrations


SQL = r'''
-- Un cambio posterior de unidad o categoría no debe reinterpretar movimientos,
-- saldos ni líneas de proforma ya existentes.
CREATE OR REPLACE FUNCTION fn_proteger_unidad_historica_producto()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.unidad_stock_id IS DISTINCT FROM OLD.unidad_stock_id
       OR NEW.categoria_id IS DISTINCT FROM OLD.categoria_id THEN
        IF OLD.stock <> 0
           OR EXISTS (SELECT 1 FROM movimientos_stock WHERE producto_id=OLD.id)
           OR EXISTS (SELECT 1 FROM proformas_detalle WHERE producto_id=OLD.id) THEN
            RAISE EXCEPTION
                'No se puede cambiar la categoría/unidad de un producto con stock, movimientos o cotizaciones históricas';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_proteger_unidad_historica_producto ON productos;
CREATE TRIGGER trg_proteger_unidad_historica_producto
BEFORE UPDATE OF unidad_stock_id, categoria_id ON productos
FOR EACH ROW EXECUTE FUNCTION fn_proteger_unidad_historica_producto();
'''

REVERSE_SQL = r'''
DROP TRIGGER IF EXISTS trg_proteger_unidad_historica_producto ON productos;
DROP FUNCTION IF EXISTS fn_proteger_unidad_historica_producto();
'''


class Migration(migrations.Migration):
    dependencies = [("proformas", "0008_ap6_caja_historica_stock")]
    operations = [migrations.RunSQL(SQL, reverse_sql=REVERSE_SQL)]
