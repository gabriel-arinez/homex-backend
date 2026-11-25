"""Triggers PostgreSQL de integridad entre órdenes de trabajo y pedidos."""

from django.db import migrations

FORWARD_SQL = """
CREATE OR REPLACE FUNCTION public.fn_bloquear_listo_entrega_sin_ot_terminada()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_tiene_muebles BOOLEAN;
    v_tiene_ot_no_terminada BOOLEAN;
    v_tiene_ot_terminada BOOLEAN;
BEGIN
    IF NEW.estado_id IS NOT DISTINCT FROM OLD.estado_id THEN
        RETURN NEW;
    END IF;

    IF NOT fn_catalogo_valor_es(NEW.estado_id, 'ESTADO_PEDIDO', 'LISTO_ENTREGA') THEN
        RETURN NEW;
    END IF;

    SELECT EXISTS(
        SELECT 1
          FROM proformas_detalle pd
         WHERE pd.proforma_id = NEW.proforma_id
           AND fn_catalogo_valor_es(pd.tipo_item_id, 'TIPO_ITEM', 'MUEBLE_MEDIDA')
    ) INTO v_tiene_muebles;

    IF NOT v_tiene_muebles THEN
        RETURN NEW;
    END IF;

    SELECT EXISTS(
        SELECT 1
          FROM ordenes_trabajo ot
         WHERE ot.pedido_id = NEW.id
           AND NOT fn_catalogo_valor_es(ot.estado_id, 'ESTADO_ORDEN_TRABAJO', 'TERMINADA')
           AND NOT fn_catalogo_valor_es(ot.estado_id, 'ESTADO_ORDEN_TRABAJO', 'CANCELADA')
    ) INTO v_tiene_ot_no_terminada;

    SELECT EXISTS(
        SELECT 1
          FROM ordenes_trabajo ot
         WHERE ot.pedido_id = NEW.id
           AND fn_catalogo_valor_es(ot.estado_id, 'ESTADO_ORDEN_TRABAJO', 'TERMINADA')
    ) INTO v_tiene_ot_terminada;

    IF v_tiene_ot_no_terminada OR NOT v_tiene_ot_terminada THEN
        RAISE EXCEPTION 'No puede marcar el pedido como LISTO_ENTREGA mientras existan órdenes de trabajo sin terminar';
    END IF;

    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS trg_bloquear_listo_entrega_sin_ot_terminada ON pedidos;
CREATE TRIGGER trg_bloquear_listo_entrega_sin_ot_terminada
BEFORE UPDATE OF estado_id ON pedidos
FOR EACH ROW
EXECUTE FUNCTION public.fn_bloquear_listo_entrega_sin_ot_terminada();

CREATE OR REPLACE FUNCTION public.fn_bloquear_cancelacion_independiente_ot()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_pedido_estado_id BIGINT;
BEGIN
    IF NEW.estado_id IS NOT DISTINCT FROM OLD.estado_id THEN
        RETURN NEW;
    END IF;

    IF NOT fn_catalogo_valor_es(NEW.estado_id, 'ESTADO_ORDEN_TRABAJO', 'CANCELADA') THEN
        RETURN NEW;
    END IF;

    SELECT p.estado_id
      INTO v_pedido_estado_id
      FROM pedidos p
     WHERE p.id = NEW.pedido_id;

    IF v_pedido_estado_id IS NOT NULL
       AND NOT fn_catalogo_valor_es(v_pedido_estado_id, 'ESTADO_PEDIDO', 'CANCELADO') THEN
        RAISE EXCEPTION 'No puede cancelar una orden de trabajo mientras el pedido siga activo';
    END IF;

    RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS trg_bloquear_cancelacion_independiente_ot ON ordenes_trabajo;
CREATE TRIGGER trg_bloquear_cancelacion_independiente_ot
BEFORE UPDATE OF estado_id ON ordenes_trabajo
FOR EACH ROW
EXECUTE FUNCTION public.fn_bloquear_cancelacion_independiente_ot();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS trg_bloquear_cancelacion_independiente_ot ON ordenes_trabajo;
DROP FUNCTION IF EXISTS public.fn_bloquear_cancelacion_independiente_ot();
DROP TRIGGER IF EXISTS trg_bloquear_listo_entrega_sin_ot_terminada ON pedidos;
DROP FUNCTION IF EXISTS public.fn_bloquear_listo_entrega_sin_ot_terminada();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("ordenes_trabajo", "0002_historialestadoordentrabajo"),
        ("pedidos", "0002_pedido_fecha_entrega_efectiva"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
