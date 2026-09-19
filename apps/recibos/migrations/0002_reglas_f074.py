from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("recibos", "0001_initial"), ("movimientos_stock", "0002_refuerzo_t05_f073")]
    operations = [
        migrations.RunSQL(
            """
CREATE OR REPLACE FUNCTION fn_preparar_recibo()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_total NUMERIC(14,2); v_pagado NUMERIC(14,2);
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF OLD.estado = 'ANULADO' OR NEW.estado NOT IN ('EMITIDO','ANULADO')
       OR (OLD.estado = 'EMITIDO' AND NEW.estado = 'EMITIDO'
           AND NEW IS DISTINCT FROM OLD) THEN
      RAISE EXCEPTION 'Un recibo emitido sólo puede anularse; no admite edición comercial';
    END IF;
    IF OLD.estado = 'EMITIDO' AND NEW.estado = 'ANULADO' THEN RETURN NEW; END IF;
  END IF;
  IF NEW.estado <> 'EMITIDO' THEN RAISE EXCEPTION 'Un recibo nuevo debe emitirse'; END IF;
  PERFORM 1 FROM pedidos WHERE id=NEW.pedido_id FOR UPDATE;
  IF NOT FOUND OR EXISTS (SELECT 1 FROM pedidos p JOIN catalogo_valores e ON e.id=p.estado_id WHERE p.id=NEW.pedido_id AND e.codigo='CANCELADO') THEN RAISE EXCEPTION 'No se cobra un pedido cancelado o inexistente'; END IF;
  SELECT p.total INTO v_total FROM pedidos pe JOIN proformas p ON p.id=pe.proforma_id WHERE pe.id=NEW.pedido_id;
  SELECT COALESCE(SUM(pago_actual),0) INTO v_pagado FROM recibos WHERE pedido_id=NEW.pedido_id AND estado='EMITIDO' AND (TG_OP='INSERT' OR id<>OLD.id);
  IF v_pagado+NEW.pago_actual>v_total THEN RAISE EXCEPTION 'El pago excede el total'; END IF;
  NEW.total:=v_total; NEW.a_cuenta:=v_pagado+NEW.pago_actual; NEW.saldo:=v_total-NEW.a_cuenta; RETURN NEW;
END; $$;
CREATE OR REPLACE FUNCTION fn_bloquear_delete_recibo() RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Los recibos no se eliminan; use ANULADO'; END; $$;
DROP TRIGGER IF EXISTS trg_bloquear_delete_recibo ON recibos;
CREATE TRIGGER trg_bloquear_delete_recibo BEFORE DELETE ON recibos FOR EACH ROW EXECUTE FUNCTION fn_bloquear_delete_recibo();
CREATE OR REPLACE FUNCTION fn_validar_nota_entrega() RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pedidos p JOIN catalogo_valores e ON e.id=p.estado_id WHERE p.id=NEW.pedido_id AND e.codigo='LISTO_ENTREGA') THEN RAISE EXCEPTION 'La nota sólo se emite desde LISTO_ENTREGA'; END IF; RETURN NEW; END; $$;
CREATE TRIGGER trg_validar_nota_entrega BEFORE INSERT ON notas_entrega FOR EACH ROW EXECUTE FUNCTION fn_validar_nota_entrega();
CREATE OR REPLACE FUNCTION fn_bloquear_cancelacion_con_cobros() RETURNS TRIGGER LANGUAGE plpgsql AS $$ BEGIN
  IF EXISTS (SELECT 1 FROM catalogo_valores WHERE id=NEW.estado_id AND codigo='CANCELADO')
     AND NOT EXISTS (SELECT 1 FROM catalogo_valores WHERE id=OLD.estado_id AND codigo='CANCELADO')
     AND EXISTS (SELECT 1 FROM recibos WHERE pedido_id=NEW.id AND estado='EMITIDO') THEN
    RAISE EXCEPTION 'No se puede cancelar un pedido con recibos emitidos';
  END IF;
  RETURN NEW;
END; $$;
DROP TRIGGER IF EXISTS trg_bloquear_cancelacion_con_cobros ON pedidos;
CREATE TRIGGER trg_bloquear_cancelacion_con_cobros BEFORE UPDATE OF estado_id ON pedidos FOR EACH ROW EXECUTE FUNCTION fn_bloquear_cancelacion_con_cobros();
""",
            """
DROP TRIGGER IF EXISTS trg_bloquear_cancelacion_con_cobros ON pedidos;
DROP FUNCTION IF EXISTS fn_bloquear_cancelacion_con_cobros();
DROP TRIGGER IF EXISTS trg_bloquear_delete_recibo ON recibos;
DROP FUNCTION IF EXISTS fn_bloquear_delete_recibo();
DROP TRIGGER IF EXISTS trg_validar_nota_entrega ON notas_entrega;
DROP FUNCTION IF EXISTS fn_validar_nota_entrega();
""",
        )
    ]
