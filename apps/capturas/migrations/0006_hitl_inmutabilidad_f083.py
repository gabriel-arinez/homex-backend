from django.db import migrations


FORWARD_SQL = """
CREATE OR REPLACE FUNCTION fn_proteger_item_humano_final()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'items_humano conserva una corrección final inmutable';
END;
$$;

CREATE TRIGGER trg_proteger_item_humano_final
BEFORE UPDATE OR DELETE ON items_humano
FOR EACH ROW
EXECUTE FUNCTION fn_proteger_item_humano_final();

CREATE OR REPLACE FUNCTION fn_proteger_evaluacion_nlp_final()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'evaluaciones_nlp conserva una evaluación final inmutable';
END;
$$;

CREATE TRIGGER trg_proteger_evaluacion_nlp_final
BEFORE UPDATE OR DELETE ON evaluaciones_nlp
FOR EACH ROW
EXECUTE FUNCTION fn_proteger_evaluacion_nlp_final();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS trg_proteger_evaluacion_nlp_final ON evaluaciones_nlp;
DROP FUNCTION IF EXISTS fn_proteger_evaluacion_nlp_final();
DROP TRIGGER IF EXISTS trg_proteger_item_humano_final ON items_humano;
DROP FUNCTION IF EXISTS fn_proteger_item_humano_final();
"""


class Migration(migrations.Migration):
    dependencies = [("capturas", "0005_db04_capturas_outbox_inmutabilidad")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
