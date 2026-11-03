# Creación de catálogo por voz

`POST /api/v1/capturas/catalogo/` recibe exactamente un audio o texto, categoría
explícita (`SILLA`, `PISO_FLOTANTE`, `OTRO`), sesión UUID e idempotencia UUID.
Una reinterpretación puede referenciar `captura_origen`, del mismo actor, sesión
y categoría. Cada captura conserva su texto y la cadena mantiene el ASR original.
`GET /api/v1/capturas/catalogo/{id}/` devuelve estado, transcripción, campos
sugeridos, evidencias, advertencias y fragmentos no reconocidos.

La migración 0010 añade exclusivamente contexto e integridad de capturas.
Se reutilizan audio temporal, Whisper Small CPU/int8, caché, outbox, Celery,
fencing, trazabilidad, autorización e idempotencia existentes. Este contexto no
crea ItemIA comercial ni escribe productos, SKU, proformas o movimientos de stock.

El permiso `catalogo.crear_producto` corresponde a administradores existentes y al
grupo `ENCARGADO_TIENDA`. Este grupo puede leer productos, familias y opciones y
crear productos; no obtiene acceso a proformas, eliminación o administración.
No cambia la pertenencia de usuarios existentes. La asignación del grupo debe
responder a la función real del usuario en cada entorno.

El paquete vendorizado es homex-nlp 0.1.20. Los IDs proceden de valores/conceptos
activos. Las sugerencias usan los tipos DRF del formulario real y las unidades
permitidas por categoría; el guardado manual revalida el serializer completo.
No se infiere precio unitario a partir de un total ni stock desde una cantidad.

Prueba local: iniciar sesión, Productos → categoría → Nuevo producto; grabar y
detener o seleccionar archivo; Procesar audio; revisar y editar transcripción;
Reinterpretar texto si cambió; Aplicar al formulario; confirmar conflictos;
completar SKU y campos obligatorios; Guardar producto manualmente.

## Auditoría de corrección

La referencia inicial fue NLP 736, Django/PostgreSQL 470, Vue 204 y E2E 96
aprobadas. Se reprodujeron pérdida de nombres naturales y medidas orales,
códigos truncados y ausencia del color secundario en el contrato/aplicación.
El paquete 0.1.21 corrige la extracción; este consumidor comparte validadores
manuales y marca como no resuelta la evidencia de los campos que descarta.

Los dos jobs de integración generan silla/piso/otro con eSpeak NG y ejecutan
once pruebas sin omisiones; la configuración incompleta produce error.
Cada caso comprueba inventario, aplicación y guardado manual. Los reportes JSON,
transcripciones y revisiones exactas se publican como artefactos aun si el job falla.
`workflow_dispatch.integration_peer_ref` permite repetir el CI contra el HEAD
final del otro repositorio; el valor por defecto fija la revisión coordinada.

Whisper Small CPU/int8 y el cache no cambian. Errores ASR como «espuma inectana»
no se convierten en características inventadas: se corrige y reinterpreta el texto.
Los fixtures sintéticos prueban la integración, no WER con voz humana.
