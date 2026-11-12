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

## Consumidor0.1.22 — auditoría de voz real

La rama de integración fija `homex-nlp==0.1.22` al wheel local versionado
`vendor/homex_nlp-0.1.22-py3-none-any.whl`, SHA-256
`c1a085f899a9f2f0797f332304fcf8eeea91f4837d5d06a9a2ca5a6c07815a80`.
El wheel0.1.21 anterior se conserva sin modificaciones. El guard del adaptador
admite0.1.22 y mantiene el contrato1.0/RULES_ONLY; no se relajan permisos,
validadores ni estados comerciales.

Las pruebas deben importar desde `site-packages` del entorno del consumidor,
no mediante `PYTHONPATH` hacia las fuentes NLP. Ejemplo de comprobación:

```bash
uv sync --locked --extra dev --extra worker
.venv/bin/python -I -c 'import homex_nlp; print(homex_nlp.__version__, homex_nlp.__file__)'
```

La propuesta sigue siendo una sugerencia revisable. Los casos de desarrollo,
las métricas con sus denominadores y las pruebas de cuatro formularios se
conservan en la rama NLP `feat/real-voice-120-results`, bajo
`audit/real-voice-120/`. Una mejora de cobertura escalar no demuestra precisión
comercial completa ni validación acústica humana. No hay despliegue ni fusión
a main implícitos.

### Gate operativo F08.4

El verificador de integración fija la distribución operativa0.1.22 y su SHA-256
publicado, además de comprobar por separado el wheel histórico F08. No basta
con conservar el archivo0.1.21 en vendor: el gate debe verificar el paquete que
realmente consume el worker. Las regresiones cubren versión desconocida y
corrupción de ambos wheels; esos errores deben detenerse antes de contactar Redis.
