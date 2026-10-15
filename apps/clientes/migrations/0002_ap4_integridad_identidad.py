from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION fn_proteger_tipo_cliente()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.tipo_cliente_id IS DISTINCT FROM OLD.tipo_cliente_id THEN
    RAISE EXCEPTION 'El tipo de cliente es inmutable';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_proteger_tipo_cliente ON clientes;
CREATE TRIGGER trg_proteger_tipo_cliente
BEFORE UPDATE OF tipo_cliente_id
ON clientes
FOR EACH ROW EXECUTE FUNCTION fn_proteger_tipo_cliente();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS trg_proteger_tipo_cliente ON clientes;
DROP FUNCTION IF EXISTS fn_proteger_tipo_cliente();
"""


class Migration(migrations.Migration):
    dependencies = [("clientes", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
