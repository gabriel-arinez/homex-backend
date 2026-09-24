from django.db import migrations


FORWARD_SQL = """
CREATE OR REPLACE FUNCTION fn_crear_outbox_intento()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trabajos_outbox (
        intento_id,
        tipo,
        clave_unica,
        disponible_at,
        intentos_publicacion
    ) VALUES (
        NEW.id,
        'PROCESAR_CAPTURA',
        'captura:' || NEW.captura_id || ':intento:' || NEW.numero_intento,
        CURRENT_TIMESTAMP,
        0
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_crear_outbox_intento ON intentos_captura;
CREATE TRIGGER trg_crear_outbox_intento
AFTER INSERT ON intentos_captura
FOR EACH ROW
EXECUTE FUNCTION fn_crear_outbox_intento();

DROP TRIGGER IF EXISTS trg_proteger_resultado_intento ON intentos_captura;
DROP FUNCTION IF EXISTS fn_bloquear_update_resultado_intento();
CREATE OR REPLACE FUNCTION fn_proteger_intento_cerrado()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.estado IN ('FINALIZADO', 'ERROR') THEN
        RAISE EXCEPTION 'Un intento cerrado es inmutable';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER trg_proteger_intento_cerrado
BEFORE UPDATE OR DELETE ON intentos_captura
FOR EACH ROW
EXECUTE FUNCTION fn_proteger_intento_cerrado();

DROP TRIGGER IF EXISTS trg_bloquear_update_item_ia ON items_ia;
DROP FUNCTION IF EXISTS fn_bloquear_update_item_ia();
CREATE OR REPLACE FUNCTION fn_proteger_item_ia()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'items_ia es evidencia inmutable';
END;
$$;

CREATE TRIGGER trg_proteger_item_ia
BEFORE UPDATE OR DELETE ON items_ia
FOR EACH ROW
EXECUTE FUNCTION fn_proteger_item_ia();
"""


REVERSE_SQL = """
DROP TRIGGER IF EXISTS trg_proteger_item_ia ON items_ia;
DROP FUNCTION IF EXISTS fn_proteger_item_ia();
CREATE OR REPLACE FUNCTION fn_bloquear_update_item_ia()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'items_ia es evidencia inmutable';
END;
$$;
CREATE TRIGGER trg_bloquear_update_item_ia BEFORE UPDATE ON items_ia
FOR EACH ROW EXECUTE FUNCTION fn_bloquear_update_item_ia();
DROP TRIGGER IF EXISTS trg_proteger_intento_cerrado ON intentos_captura;
DROP FUNCTION IF EXISTS fn_proteger_intento_cerrado();
CREATE OR REPLACE FUNCTION fn_bloquear_update_resultado_intento()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.estado IN ('FINALIZADO', 'ERROR')
       AND NEW.resultado_raw IS DISTINCT FROM OLD.resultado_raw THEN
        RAISE EXCEPTION 'El resultado de un intento cerrado es inmutable';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_proteger_resultado_intento BEFORE UPDATE ON intentos_captura
FOR EACH ROW EXECUTE FUNCTION fn_bloquear_update_resultado_intento();
DROP TRIGGER IF EXISTS trg_crear_outbox_intento ON intentos_captura;
CREATE OR REPLACE FUNCTION fn_crear_outbox_intento()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO trabajos_outbox (
        intento_id, tipo, clave_unica, disponible_at, intentos_publicacion
    ) VALUES (
        NEW.id, 'PROCESAR_CAPTURA',
        'captura-' || NEW.captura_id || '-intento-' || NEW.numero_intento,
        CURRENT_TIMESTAMP, 0
    );
    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_crear_outbox_intento AFTER INSERT ON intentos_captura
FOR EACH ROW EXECUTE FUNCTION fn_crear_outbox_intento();
"""


class Migration(migrations.Migration):
    dependencies = [("capturas", "0004_cierre_integridad_f071_f072")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
