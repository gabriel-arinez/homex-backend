from django.db import migrations

FORWARD_SQL = """
DROP INDEX IF EXISTS ix_productos_activos_nombre;
DROP INDEX IF EXISTS ix_proformas_vendedor_estado_fecha;
DROP INDEX IF EXISTS ix_proformas_detalle_producto;
DROP INDEX IF EXISTS ix_notas_entrega_fecha;

CREATE INDEX ix_productos_nombre_id
ON productos (nombre, id);

CREATE INDEX ix_proformas_vendedor_id_desc
ON proformas (vendedor_id, id DESC);
"""


REVERSE_SQL = """
DROP INDEX IF EXISTS ix_proformas_vendedor_id_desc;
DROP INDEX IF EXISTS ix_productos_nombre_id;

CREATE INDEX ix_productos_activos_nombre
ON productos (nombre, id)
WHERE activo;

CREATE INDEX ix_proformas_vendedor_estado_fecha
ON proformas (vendedor_id, estado_id, fecha DESC);

CREATE INDEX ix_proformas_detalle_producto
ON proformas_detalle (producto_id)
WHERE producto_id IS NOT NULL;

CREATE INDEX ix_notas_entrega_fecha
ON notas_entrega (fecha DESC);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0002_indices_operativos_f076"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        )
    ]
