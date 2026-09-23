# F07.7 — Media persistente y almacenamiento de objetos

## Estado

Implementación local validada.

La fase todavía no se declara cerrada porque falta ejecutar y confirmar el
CI remoto de GitHub Actions sobre el commit correctivo.

## Base de trabajo

- Rama: `re-refactor`
- Commit F07.7 publicado originalmente:
  `677e5380ee4523ed09c9e0cfe75fe39f0cb2a2e1`
- El primer CI remoto de F07.7 falló porque `apps/media/` fue excluido
  accidentalmente por la regla `media/` de `.gitignore`.
- La corrección cambia esa regla por rutas explícitas de media local y añade
  `apps/media` al repositorio.

## Objetivo

Implementar media persistente pública para imágenes comerciales de HOMEX,
manteniendo PostgreSQL únicamente como autoridad de metadatos y object keys.

El audio del pipeline ASR/NLP permanece fuera de este flujo persistente.

## Storage

### Desarrollo y pruebas

Se utiliza `FileSystemStorage` mediante `STORAGES`.

No se requieren credenciales R2 para ejecutar desarrollo, tests ni CI.

### Producción

Se utiliza Cloudflare R2 Standard mediante la interfaz S3-compatible y
`django-storages`.

Bucket productivo congelado:

`homex-public-media`

Prefijos:

- `productos/`
- `proformas/`

Variables requeridas:

- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_ENDPOINT_URL`
- `R2_BUCKET_NAME`
- `HOMEX_MEDIA_PUBLIC_DOMAIN`

Las variables se documentan en `.env.example` únicamente con placeholders.

Producción falla explícitamente si falta una variable requerida o si
`R2_BUCKET_NAME` no es `homex-public-media`.

No se configura ACL por objeto mediante `default_acl`. La lectura pública se
resuelve mediante la configuración pública del bucket/dominio de medios.

## Dependencias

La implementación utiliza dependencias bloqueadas en `pyproject.toml` y
`uv.lock`:

- `django-storages`
- `boto3`
- `Pillow`

## Modelo y migraciones

### Catálogo

`catalogo.0006_media_persistente_f077` incorpora:

- `Producto.imagen_principal`
- `Producto.imagen_principal_variantes`

`catalogo.0007_media_dimensiones_f077` incorpora:

- `Producto.imagen_principal_dimensiones`

Las dimensiones persistidas corresponden a la imagen normalizada después de
corregir orientación EXIF y permiten al frontend reservar el espacio visual sin
consultar el objeto remoto.

### Documentos

`documentos.0004_media_persistente_f077` incorpora la asociación opcional entre
`ArchivoAdjunto` y `DetalleProforma`.

`documentos.0005_integridad_adjunto_f077` incorpora integridad PostgreSQL para
impedir asociar un detalle perteneciente a otra proforma.

## Object keys

`ruta_storage` almacena únicamente una object key estable.

Nunca se persisten:

- URL completa del proveedor;
- endpoint R2;
- bucket como parte del contrato del cliente;
- nombre proporcionado por el usuario como ruta definitiva.

Las keys se generan bajo identificadores UUID.

Ejemplos conceptuales:

- `productos/<uuid>/original.webp`
- `productos/<uuid>/320.webp`
- `productos/<uuid>/640.webp`
- `productos/<uuid>/1280.webp`
- `proformas/<uuid>/original.webp`

## Procesamiento de imágenes

Formatos admitidos:

- JPEG
- PNG
- WebP

SVG y contenido no-imagen son rechazados.

Límite:

- 10 MiB por imagen

El backend:

1. valida MIME permitido;
2. decodifica el contenido real mediante Pillow;
3. corrige orientación EXIF;
4. reescribe la imagen como WebP;
5. elimina metadatos EXIF innecesarios;
6. genera variantes WebP 320/640/1280;
7. no amplía imágenes menores;
8. genera object keys no controladas por el usuario.

La versión normalizada del original también se almacena como WebP.

## Imagen principal de producto

Producto mantiene una única imagen principal opcional.

La respuesta pública contiene:

- `original`
- `ancho`
- `alto`
- `variantes`

La ausencia de imagen sigue siendo válida.

Las mutaciones de imagen principal requieren administración comercial.

El reemplazo:

- actualiza la referencia DB;
- elimina los objetos anteriores después del commit;
- elimina los nuevos objetos si el almacenamiento falla antes de completar la
  operación.

La eliminación limpia original y variantes.

## Adjuntos de proforma

`ArchivoAdjunto` continúa siendo la autoridad de metadatos.

Los adjuntos de F07.7:

- pertenecen a una proforma;
- pueden asociarse a un detalle;
- sólo se modifican cuando la proforma está en `BORRADOR`;
- validan que el detalle pertenece a la misma proforma;
- rechazan audio;
- almacenan key y no URL.

Un vendedor ajeno recibe `403` en las operaciones específicas de media de una
proforma fuera de su alcance.

## Endpoints

Implementados:

```text
POST   /api/v1/catalogo/productos/{id}/imagen-principal/
DELETE /api/v1/catalogo/productos/{id}/imagen-principal/

GET    /api/v1/proformas/{id}/detalles/{detalle_id}/archivos/
POST   /api/v1/proformas/{id}/detalles/{detalle_id}/archivos/
DELETE /api/v1/proformas/{id}/detalles/{detalle_id}/archivos/{archivo_id}/