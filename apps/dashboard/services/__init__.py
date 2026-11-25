from apps.dashboard.services.alertas import obtener_alertas_prioritarias_admin
from apps.dashboard.services.comercial import (
    obtener_agenda_comercial,
    obtener_comparacion_vendedores,
    obtener_evolucion_comercial,
    obtener_indicadores_comerciales,
)
from apps.dashboard.services.common import fecha_referencia_analitica
from apps.dashboard.services.finanzas import (
    obtener_finanzas_admin,
    obtener_resumen_financiero_vendedor,
)
from apps.dashboard.services.inventario import (
    obtener_disponibilidad_comercial,
    obtener_inventario_admin,
)
from apps.dashboard.services.taller import (
    obtener_cola_prioridades_taller,
    obtener_dashboard_taller,
    obtener_planificacion_taller,
    obtener_resumen_produccion_admin,
)

__all__ = [
    "fecha_referencia_analitica",
    "obtener_agenda_comercial",
    "obtener_alertas_prioritarias_admin",
    "obtener_cola_prioridades_taller",
    "obtener_comparacion_vendedores",
    "obtener_dashboard_taller",
    "obtener_disponibilidad_comercial",
    "obtener_evolucion_comercial",
    "obtener_finanzas_admin",
    "obtener_indicadores_comerciales",
    "obtener_inventario_admin",
    "obtener_planificacion_taller",
    "obtener_resumen_financiero_vendedor",
    "obtener_resumen_produccion_admin",
]
