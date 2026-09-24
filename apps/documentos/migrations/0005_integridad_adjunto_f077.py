from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("documentos", "0004_media_persistente_f077")]
    operations = [migrations.RunSQL(
        """
CREATE OR REPLACE FUNCTION fn_validar_adjunto_detalle_proforma()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.proforma_detalle_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM proformas_detalle d WHERE d.id=NEW.proforma_detalle_id AND d.proforma_id=NEW.proforma_id
  ) THEN RAISE EXCEPTION 'El detalle adjunto debe pertenecer a la misma proforma'; END IF;
  RETURN NEW;
END; $$;
CREATE TRIGGER trg_validar_adjunto_detalle_proforma BEFORE INSERT OR UPDATE ON archivos_adjuntos FOR EACH ROW EXECUTE FUNCTION fn_validar_adjunto_detalle_proforma();
""",
        "DROP TRIGGER IF EXISTS trg_validar_adjunto_detalle_proforma ON archivos_adjuntos; DROP FUNCTION IF EXISTS fn_validar_adjunto_detalle_proforma();",
    )]
