# Vigencia y estados de proformas

La fecha de creación más los días de validez determina el último día completo de vigencia, en la zona horaria configurada. Por ejemplo, una proforma creada el 6 con validez de 5 días permanece vigente hasta el final del 11 y vence el 12. Sin plazo no vence automáticamente.

La tarea `proformas.vencer` se programa cada 60 segundos mediante Celery Beat y cambia únicamente proformas `EN_REVISION` vencidas a `VENCIDA`. Requiere que el worker y Beat estén activos; si no lo están, el estado visible puede quedar desactualizado hasta que se ejecute la tarea. La aprobación y las demás modificaciones comerciales rechazan las proformas vencidas incluso antes de la ejecución de la tarea. Las proformas aprobadas y anuladas no se modifican.

La migración `0013_desactivar_estados_sin_uso` desactiva las opciones `ENVIADA` y `RECHAZADA` sin borrar valores ni referencias históricas. Su reversión no reactiva automáticamente los valores, pues no se conoce su estado previo.
