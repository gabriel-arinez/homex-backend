from django.db import migrations

CREATE_GUARDS = """
CREATE OR REPLACE FUNCTION homex_guard_stock_directo()
RETURNS trigger AS $$
BEGIN
    IF NEW.stock IS DISTINCT FROM OLD.stock
       AND current_setting('homex.stock_change', true) IS DISTINCT FROM 'allowed' THEN
        RAISE EXCEPTION 'El stock sólo cambia mediante movimientos_stock';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION homex_aplicar_movimiento_stock()
RETURNS trigger AS $$
BEGIN
    PERFORM set_config('homex.stock_change', 'allowed', true);
    UPDATE productos
       SET stock = stock + NEW.quantity
     WHERE id = NEW.product_id
       AND stock + NEW.quantity >= 0;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Stock insuficiente o producto inexistente';
    END IF;
    PERFORM set_config('homex.stock_change', '', true);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION homex_guard_movimiento_inmutable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Los movimientos de stock son inmutables';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_productos_stock_directo
BEFORE UPDATE OF stock ON productos
FOR EACH ROW EXECUTE FUNCTION homex_guard_stock_directo();

CREATE TRIGGER trg_movimientos_aplicar_stock
BEFORE INSERT ON movimientos_stock
FOR EACH ROW EXECUTE FUNCTION homex_aplicar_movimiento_stock();

CREATE TRIGGER trg_movimientos_inmutables
BEFORE UPDATE OR DELETE ON movimientos_stock
FOR EACH ROW EXECUTE FUNCTION homex_guard_movimiento_inmutable();
"""

DROP_GUARDS = """
DROP TRIGGER IF EXISTS trg_movimientos_inmutables ON movimientos_stock;
DROP TRIGGER IF EXISTS trg_movimientos_aplicar_stock ON movimientos_stock;
DROP TRIGGER IF EXISTS trg_productos_stock_directo ON productos;
DROP FUNCTION IF EXISTS homex_guard_movimiento_inmutable();
DROP FUNCTION IF EXISTS homex_aplicar_movimiento_stock();
DROP FUNCTION IF EXISTS homex_guard_stock_directo();
"""


def create_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(CREATE_GUARDS)


def drop_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DROP_GUARDS)


class Migration(migrations.Migration):
    dependencies = [("inventory", "0004_stockmovement_observations")]

    operations = [migrations.RunPython(create_guards, drop_guards)]
