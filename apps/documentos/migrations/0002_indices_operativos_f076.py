from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0001_initial"),
        ("proformas", "0004_cierre_reglas_f072"),
        ("recibos", "0003_cierre_reglas_f074"),
    ]

    operations = [
        migrations.RunSQL(
            """
CREATE INDEX ix_productos_activos_nombre ON productos (nombre, id) WHERE activo;
CREATE INDEX ix_proformas_vendedor_estado_fecha ON proformas (vendedor_id, estado_id, fecha DESC);
CREATE INDEX ix_proformas_detalle_producto ON proformas_detalle (producto_id) WHERE producto_id IS NOT NULL;
CREATE INDEX ix_recibos_pedido_emitidos ON recibos (pedido_id) WHERE estado = 'EMITIDO';
CREATE INDEX ix_notas_entrega_fecha ON notas_entrega (fecha DESC);
""",
            """
DROP INDEX IF EXISTS ix_notas_entrega_fecha;
DROP INDEX IF EXISTS ix_recibos_pedido_emitidos;
DROP INDEX IF EXISTS ix_proformas_detalle_producto;
DROP INDEX IF EXISTS ix_proformas_vendedor_estado_fecha;
DROP INDEX IF EXISTS ix_productos_activos_nombre;
""",
        )
    ]
