from django.db import migrations


FORWARD_SQL = """
CREATE OR REPLACE FUNCTION fn_proteger_vinculo_captura_f083()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.proforma_detalle_id IS NOT NULL
       AND NEW.proforma_detalle_id IS DISTINCT FROM OLD.proforma_detalle_id THEN
        RAISE EXCEPTION 'capturas.proforma_detalle_id es inmutable una vez establecido';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_proteger_vinculo_captura_f083 ON capturas;
CREATE TRIGGER trg_proteger_vinculo_captura_f083
BEFORE UPDATE OF proforma_detalle_id ON capturas
FOR EACH ROW
EXECUTE FUNCTION fn_proteger_vinculo_captura_f083();
"""


REVERSE_SQL = """
DROP TRIGGER IF EXISTS trg_proteger_vinculo_captura_f083 ON capturas;
DROP FUNCTION IF EXISTS fn_proteger_vinculo_captura_f083();
"""


class Migration(migrations.Migration):
    dependencies = [("capturas", "0006_hitl_inmutabilidad_f083")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
