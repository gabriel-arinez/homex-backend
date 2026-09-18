from django.db import migrations

CREATE_GUARDS = """
CREATE OR REPLACE FUNCTION homex_guard_recibo_inmutable()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Los recibos no se eliminan';
    END IF;
    IF OLD.status = 'EMITIDO'
       AND NEW.status = 'ANULADO'
       AND NEW.number IS NOT DISTINCT FROM OLD.number
       AND NEW.order_id IS NOT DISTINCT FROM OLD.order_id
       AND NEW.full_name IS NOT DISTINCT FROM OLD.full_name
       AND NEW.amount_in_words IS NOT DISTINCT FROM OLD.amount_in_words
       AND NEW.concept IS NOT DISTINCT FROM OLD.concept
       AND NEW.payment_type_id IS NOT DISTINCT FROM OLD.payment_type_id
       AND NEW.check_number IS NOT DISTINCT FROM OLD.check_number
       AND NEW.bank IS NOT DISTINCT FROM OLD.bank
       AND NEW.total IS NOT DISTINCT FROM OLD.total
       AND NEW.current_payment IS NOT DISTINCT FROM OLD.current_payment
       AND NEW.on_account IS NOT DISTINCT FROM OLD.on_account
       AND NEW.balance IS NOT DISTINCT FROM OLD.balance
       AND NEW.date IS NOT DISTINCT FROM OLD.date
       AND NEW.created_by_id IS NOT DISTINCT FROM OLD.created_by_id
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
    IF NEW.status <> 'EMITIDO' THEN
        RETURN NEW;
    END IF;
    SELECT q.total INTO pedido_total
      FROM pedidos p
      JOIN proformas q ON q.id = p.proforma_id
     WHERE p.id = NEW.order_id
     FOR UPDATE OF p;
    IF pedido_total IS NULL THEN
        RAISE EXCEPTION 'Pedido inexistente para recibo';
    END IF;
    SELECT COALESCE(SUM(current_payment), 0) INTO pagado
      FROM recibos
     WHERE order_id = NEW.order_id
       AND status = 'EMITIDO';
    IF pagado + NEW.current_payment > pedido_total THEN
        RAISE EXCEPTION 'El pago supera el saldo pendiente del pedido';
    END IF;
    NEW.total := pedido_total;
    NEW.on_account := pagado + NEW.current_payment;
    NEW.balance := pedido_total - NEW.on_account;
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
    dependencies = [("payments", "0001_initial")]

    operations = [migrations.RunPython(create_guards, drop_guards)]
