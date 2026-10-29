# Consumidor del motor determinístico congelado

Versión elegida: homex-nlp0.1.17, prf04-rules-final, RULES_ONLY, contrato1.0.
El wheel se conserva en vendor con su SHA256 y uv.lock. El adaptador rechaza
versiones/modos incompatibles. No se incorpora el paquete0.1.16 de PR43.

La proyección PRF04_2 conserva los unitarios explícitos aunque falte cantidad;
retiene separadamente el total literal para su revisión en el formulario. Una
referencia aproximada nunca se copia a precio_unitario. Los espesores orales
sin pieza tienen resolución ESPESOR_SIN_COMPONENTE, sin afirmar ámbito general
ni fabricar un padre. Se conservan las equivalencias de tipos existentes;
ningún código, catálogo, permiso o migración se crea por inferencia.

Comprobar `sha256sum --check vendor/homex_nlp-0.1.17.sha256`, instalar mediante
`uv sync --locked --extra dev --extra worker` en un entorno nuevo y ejecutar
pruebas contra PostgreSQL/Redis propios. La batería nueva usa adaptador y
proyector reales; incluye pendientes, cantidades, totales e idempotencia.
El frontend conserva el descuento ausente como pendiente y prevalencia de la
edición manual. Sólo la acción comercial explícita persiste el mueble.

La rama parte de main; no contiene la investigación del PR37 ni optimización
ASR del PR42. PR43 queda histórico, no es la integración final seleccionada.
No hay despliegue, reinicio de workers activos ni cambios sobre proformas reales.

## Incorporación futura, después del sistema completo

La imagen histórica observada `homex/backend:d04-9ce7230` contiene paquete0.1.0.
Adaptador y pyproject de esa imagen coincidieron con backend
9ce723048d98a3925be45d9c359a25e6be7b19f3. No se modifica durante este cierre.

Cuando se autorice una incorporación: construir imagen nueva desde el commit
consumidor definitivo y su wheel fijado, comprobar versión y hash dentro de esa
imagen, ejecutar gates aislados y seguir el procedimiento operativo del sistema.
No instalar manualmente wheels dentro del worker activo ni mezclar versiones
en una cola. Conservar rollback. Este documento no autoriza ejecutar ese cambio.

El desarrollo NLP se cierra. ASR es la siguiente etapa y debe conservar la frontera
textual del contrato1.0 sin alterar el motor congelado.
