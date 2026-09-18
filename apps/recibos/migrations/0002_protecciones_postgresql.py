from django.db import migrations

CREATE_GUARDS = """
CREATE OR REPLACE FUNCTION homex_guard_recibo_inmutable()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Los recibos no se eliminan';
    END IF;
    IF OLD.estado = 'EMITIDO'
       AND NEW.estado = 'ANULADO'
       AND NEW.numero IS NOT DISTINCT FROM OLD.numero
       AND NEW.pedido_id IS NOT DISTINCT FROM OLD.pedido_id
       AND NEW.nombre_completo IS NOT DISTINCT FROM OLD.nombre_completo
       AND NEW.monto_literal IS NOT DISTINCT FROM OLD.monto_literal
       AND NEW.concepto IS NOT DISTINCT FROM OLD.concepto
       AND NEW.tipo_pago_id IS NOT DISTINCT FROM OLD.tipo_pago_id
       AND NEW.numero_cheque IS NOT DISTINCT FROM OLD.numero_cheque
       AND NEW.banco IS NOT DISTINCT FROM OLD.banco
       AND NEW.total IS NOT DISTINCT FROM OLD.total
       AND NEW.pago_actual IS NOT DISTINCT FROM OLD.pago_actual
       AND NEW.a_cuenta IS NOT DISTINCT FROM OLD.a_cuenta
       AND NEW.saldo IS NOT DISTINCT FROM OLD.saldo
       AND NEW.fecha IS NOT DISTINCT FROM OLD.fecha
       AND NEW.creado_por_id IS NOT DISTINCT FROM OLD.creado_por_id
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'Un recibo sólo puede anularse sin alterar su evidencia';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION homex_calcular_recibo_emitido()
RETURNS trigger AS $$
DECLARE
    pedido_total NUMERIC(14,2);
    pagado NUMERIC(14,2);
BEGIN
    IF NEW.estado <> 'EMITIDO' THEN
        RETURN NEW;
    END IF;
    SELECT q.total INTO pedido_total
      FROM pedidos p
      JOIN proformas q ON q.id = p.proforma_id
     WHERE p.id = NEW.pedido_id
     FOR UPDATE OF p;
    IF pedido_total IS NULL THEN
        RAISE EXCEPTION 'Pedido inexistente para recibo';
    END IF;
    SELECT COALESCE(SUM(pago_actual), 0) INTO pagado
      FROM recibos
     WHERE pedido_id = NEW.pedido_id
       AND estado = 'EMITIDO';
    IF pagado + NEW.pago_actual > pedido_total THEN
        RAISE EXCEPTION 'El pago supera el saldo pendiente del pedido';
    END IF;
    NEW.total := pedido_total;
    NEW.a_cuenta := pagado + NEW.pago_actual;
    NEW.saldo := pedido_total - NEW.a_cuenta;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_recibos_inmutables
BEFORE UPDATE OR DELETE ON recibos
FOR EACH ROW EXECUTE FUNCTION homex_guard_recibo_inmutable();

CREATE TRIGGER trg_recibos_calcular_emitido
BEFORE INSERT ON recibos
FOR EACH ROW EXECUTE FUNCTION homex_calcular_recibo_emitido();
"""

DROP_GUARDS = """
DROP TRIGGER IF EXISTS trg_recibos_calcular_emitido ON recibos;
DROP TRIGGER IF EXISTS trg_recibos_inmutables ON recibos;
DROP FUNCTION IF EXISTS homex_calcular_recibo_emitido();
DROP FUNCTION IF EXISTS homex_guard_recibo_inmutable();
"""


def create_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(CREATE_GUARDS)


def drop_guards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DROP_GUARDS)


class Migration(migrations.Migration):
    dependencies = [("recibos", "0001_initial")]

    operations = [migrations.RunPython(create_guards, drop_guards)]
