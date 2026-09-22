# F07.7 — Media persistente y almacenamiento de objetos

## Resultado

Se incorporó media persistente pública para imágenes comerciales. PostgreSQL conserva sólo
metadatos y object keys; los binarios no se almacenan en la base de datos. El audio de ASR/NLP
sigue siendo temporal y no utiliza este flujo ni este bucket.

## Modelo y migraciones

- `catalogo.0006_media_persistente_f077`: imagen principal opcional y variantes en `Producto`.
- `documentos.0004_media_persistente_f077`: asociación opcional de `ArchivoAdjunto` con
  `DetalleProforma`.
- `documentos.0005_integridad_adjunto_f077`: trigger que exige que el detalle pertenezca a la
  misma proforma.

`ruta_storage` siempre almacena un object key generado, nunca una URL ni el nombre aportado por
la persona usuaria. Las imágenes de producto usan `productos/<uuid>/` y los adjuntos
`proformas/<uuid>/`.

## Procesamiento y endpoints

Sólo se admiten JPEG, PNG y WebP de hasta 10 MiB. Pillow decodifica, corrige orientación EXIF y
reescribe el original como WebP; genera variantes de 320, 640 y 1280 píxeles sin ampliar imágenes.
Se eliminan los objetos nuevos si falla la transacción y los objetos reemplazados o eliminados tras
el commit.

- `POST`/`DELETE` `/api/v1/catalogo/productos/{id}/imagen-principal/`
- `GET`/`POST` `/api/v1/proformas/{id}/detalles/{detalle_id}/archivos/`
- `DELETE` `/api/v1/proformas/{id}/detalles/{detalle_id}/archivos/{archivo_id}/`

Los serializers devuelven URLs públicas estables y no exponen credenciales, endpoint interno ni
nombre del bucket. La generación OpenAPI documenta las solicitudes multipart.

## Storage y configuración

Desarrollo y pruebas usan filesystem local sin credenciales. Producción requiere:

- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_ENDPOINT_URL`
- `R2_BUCKET_NAME=homex-public-media`
- `HOMEX_MEDIA_PUBLIC_DOMAIN`

Producción falla explícitamente si falta una variable o el bucket no es `homex-public-media`.
`django-storages`, `boto3` y Pillow están bloqueados en `pyproject.toml`/`uv.lock`.

## Evidencia local

- Ruff y formato: OK.
- `manage.py check`: OK.
- `makemigrations --check`: OK.
- Pruebas F07.7: 6 passed.
- Suite PostgreSQL completa: 79 passed.
- OpenAPI regenerado y validado.

La evidencia de GitHub Actions se completará cuando estos cambios sean confirmados y enviados a
la rama `re-refactor`.
