# Galerías de imágenes

## Contratos y permisos

`GET/POST/PATCH /api/v1/catalogo/productos/{id}/imagenes/` devuelve `{imagenes, limite}`. POST recibe `archivo` multipart. PATCH admite una acción: `{"principal": id}`, `{"orden": [todos_los_ids]}` o `{"eliminar": id}`. El vendedor/encargado puede crear productos y modificar sus propios productos y galerías; el administrador gestiona globalmente. El catálogo continúa siendo compartido para consulta.

`POST /api/v1/galerias/` recibe `sesion` UUID y opcionalmente `detalle` para adoptar los adjuntos existentes. Para duplicar recibe `origen` y un nuevo `id` UUID del cliente, que permite reintentar sin duplicar la copia. La copia tiene objetos independientes. `GET/POST/PATCH /api/v1/galerias/{uuid}/imagenes/` usa las mismas operaciones de galería.

El guardado integral acepta `galeria_id` por detalle y `sesion_borrador` en la cabecera. Vincula dentro de la transacción comercial, comprueba propietario, sesión, tipo de línea y vinculación previa. Un UUID vinculado a otra línea no se puede reutilizar. El replay integral conserva su idempotencia.

Los contratos anteriores `imagen-principal` y `detalles/{id}/archivos` se mantienen. `imagen_principal` sigue reflejando la portada; el orden de galería no la cambia. El borrado de portada elige la primera imagen restante por posición e ID. Las imágenes siguen siendo opcionales.

## Archivos privados y despliegue

Filesystem sigue siendo el valor predeterminado. Las referencias nuevas se almacenan en `MEDIA_ROOT/.private`, dentro del volumen persistente y de sus copias de seguridad. Se sirven como respuestas autenticadas en `/api/v1/imagenes-privadas/{id}/`, con `Cache-Control: private, no-store`. La lista por `?detalle={id}` permite al taller consultar referencias de líneas con orden de trabajo. Vendedores ajenos reciben 404. No se colocan tokens en URLs.

Es necesario actualizar también `homex-deploy`: Nginx rechaza `/media/.private/` y `/media/proformas/`; API, migrador y worker comparten el volumen persistente. La migración copia los adjuntos históricos al área privada y elimina sus antiguas claves públicas después de confirmar la transacción. Los archivos históricos ausentes conservan su referencia para reparación. Las imágenes de catálogo existentes se incorporan sin mover sus objetos ni perder variantes/dimensiones.

Para S3/R2 configura un bucket privado distinto, con acceso público deshabilitado: `R2_PRIVATE_BUCKET_NAME`. El overlay opcional `compose.s3-media.yml` configura ambos almacenamientos. No cambia el almacenamiento filesystem de instalaciones existentes. Aplica primero la configuración de privacidad del proxy y luego las migraciones/backend; finalmente, el frontend.

`HOMEX_GALLERY_MAX_IMAGES` configura la cantidad (8 por defecto). JPEG, PNG y WebP, hasta 10 MiB, se validan y decodifican en servidor. SHA-256 evita duplicados en una galería. Las mutaciones bloquean el producto o la proforma/galería para respetar límites concurrentes. Las eliminaciones de objetos se ejecutan al confirmar la transacción; las cargas fallidas limpian los objetos nuevos.

Celery Beat ejecuta diariamente `documentos.limpiar_galerias`, que elimina galerías no vinculadas con 30 días de inactividad. También se puede ejecutar:

```bash
cd /home/gabriel/HOMEX/homex-backend
.venv/bin/python manage.py limpiar_galerias --dias 30
```

## Verificación

Usa una base PostgreSQL desechable con permiso para crear la base de pruebas:

```bash
cd /home/gabriel/HOMEX/homex-backend
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py spectacular --file /tmp/homex-openapi.yaml --validate
diff -u docs/openapi.yaml /tmp/homex-openapi.yaml
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q
```

Las pruebas de `tests/api/test_galerias.py` cubren portada, orden, límites, duplicados, rollback, vínculos idempotentes, aislamiento, copias, limpieza, concurrencia, acceso de taller y migración de fotografías históricas. El frontend contiene pruebas con backend real en `src/tests/integration/galerias-real.spec.ts` y sus instrucciones en `docs/GALERIAS.md`.
