# F07.7 — Media persistente y almacenamiento de objetos

## Estado

**Fase cerrada.**

La implementación fue validada localmente y por GitHub Actions.

- Rama: `re-refactor`
- Commit correctivo funcional final:
  `48278a7e0556dd9ea2cd01d9b6c164118b2391a6`
- GitHub Actions: run #26 (`35822046560`)
- Resultado CI: **7/7 jobs verdes**

El primer commit de F07.7 (`677e5380ee4523ed09c9e0cfe75fe39f0cb2a2e1`) falló en CI porque la regla `media/` de `.gitignore` excluía accidentalmente `apps/media/`. La corrección cambió esa regla por rutas locales explícitas y versionó el módulo de media requerido.

## Objetivo

Implementar media persistente pública para imágenes comerciales de HOMEX, manteniendo PostgreSQL como autoridad de metadatos y object keys y dejando los binarios fuera de la base de datos.

El audio del pipeline ASR/NLP permanece fuera de este flujo persistente.

## Storage

### Desarrollo y pruebas

Se utiliza `FileSystemStorage` mediante `STORAGES`.

Desarrollo, tests y CI funcionan sin credenciales de Cloudflare R2.

### Producción

Producción utiliza Cloudflare R2 Standard mediante la interfaz S3-compatible, `django-storages` y `boto3`.

Bucket productivo fijado:

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

`.env.example` contiene únicamente placeholders.

Producción falla explícitamente si falta una variable obligatoria o si `R2_BUCKET_NAME` no es `homex-public-media`.

No se configura `default_acl`. La lectura pública se resuelve mediante la configuración pública del bucket y el dominio propio de medios. `querystring_auth=False` evita URLs firmadas como segunda arquitectura.

## Dependencias

La implementación utiliza dependencias bloqueadas en `pyproject.toml` y `uv.lock`:

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

Las dimensiones corresponden a la imagen normalizada después de corregir orientación EXIF y permiten al frontend reservar espacio de renderizado sin consultar el objeto remoto.

### Documentos

`documentos.0004_media_persistente_f077` incorpora la asociación opcional de `ArchivoAdjunto` con `DetalleProforma`.

`documentos.0005_integridad_adjunto_f077` impide asociar a una proforma un detalle perteneciente a otra proforma.

## Object keys

`ruta_storage` almacena una object key estable, nunca una URL del proveedor.

No se persisten como contrato comercial:

- URL completa de R2;
- endpoint interno del proveedor;
- bucket como dato requerido por Vue;
- nombre aportado por el usuario como ruta definitiva.

Las keys se generan con identificadores UUID.

Ejemplos conceptuales:

- `productos/<uuid>/original.webp`
- `productos/<uuid>/320.webp`
- `productos/<uuid>/640.webp`
- `productos/<uuid>/1280.webp`
- `proformas/<uuid>/original.webp`

## Procesamiento de imágenes

Formatos de entrada admitidos:

- JPEG
- PNG
- WebP

SVG, audio y contenido no-imagen se rechazan.

Límite:

- 10 MiB por imagen

El backend:

1. valida MIME permitido;
2. decodifica el contenido real con Pillow;
3. corrige orientación EXIF;
4. reescribe el original normalizado como WebP;
5. elimina metadatos EXIF innecesarios;
6. genera variantes WebP de 320, 640 y 1280 px;
7. no amplía originales menores;
8. genera nombres y object keys controlados por HOMEX;
9. elimina objetos creados parcialmente si el storage falla.

## Imagen principal de producto

Producto conserva una única imagen principal opcional.

La respuesta pública contiene:

- `original`
- `ancho`
- `alto`
- `variantes`

La ausencia de imagen es válida.

Las mutaciones de imagen principal requieren administración comercial.

El reemplazo actualiza la referencia DB y las dimensiones; los objetos antiguos se eliminan después del commit. Si falla la operación antes de completar la persistencia, se limpian los objetos nuevos.

La eliminación limpia original, variantes y dimensiones.

## Adjuntos de proforma

`ArchivoAdjunto` continúa siendo la autoridad de metadatos.

Reglas verificadas:

- pertenece a una proforma;
- puede asociarse a un detalle;
- el detalle debe pertenecer a la misma proforma;
- sólo se modifica según el estado permitido de la proforma;
- audio se rechaza;
- `ruta_storage` almacena key y no URL;
- un vendedor ajeno recibe `403` en operaciones de media fuera de su alcance.

## Endpoints

Implementados:

```text
POST   /api/v1/catalogo/productos/{id}/imagen-principal/
DELETE /api/v1/catalogo/productos/{id}/imagen-principal/

GET    /api/v1/proformas/{id}/detalles/{detalle_id}/archivos/
POST   /api/v1/proformas/{id}/detalles/{detalle_id}/archivos/
DELETE /api/v1/proformas/{id}/detalles/{detalle_id}/archivos/{archivo_id}/
```

Las cargas utilizan `multipart/form-data`.

La API no expone credenciales, endpoint interno R2 ni exige que el cliente conozca el bucket.

## Pruebas específicas F07.7

La cobertura específica valida:

- JPEG, PNG y WebP;
- rechazo de SVG, audio y contenido falso;
- límite de 10 MiB;
- orientación EXIF;
- eliminación de metadatos innecesarios;
- variantes 320/640/1280;
- no upscale;
- dimensiones persistidas;
- nombres no controlados por el usuario;
- reemplazo y eliminación;
- limpieza de huérfanos;
- fallo parcial de storage;
- asociación proforma/detalle;
- permisos de vendedor;
- `403` fuera de alcance;
- permisos administrativos de imagen de producto;
- errores 4xx controlados;
- configuración productiva R2;
- OpenAPI sin configuración interna del proveedor.

Resultado:

```text
22 passed
```

## Gates locales de cierre

- `uv sync --locked --extra dev`: OK
- `ruff check .`: OK
- `ruff format --check .`: OK
- `manage.py check`: OK
- `makemigrations --check --dry-run`: sin cambios
- suite PostgreSQL completa: **95 passed**
- concurrencia: **9 passed, 86 deselected**
- OpenAPI: validado y sin drift
- `git diff --check`: limpio

## Migración desde PostgreSQL vacío

Se verificó una base PostgreSQL descartable desde cero.

Migraciones relevantes:

- `catalogo.0006_media_persistente_f077`
- `catalogo.0007_media_dimensiones_f077`
- `documentos.0004_media_persistente_f077`
- `documentos.0005_integridad_adjunto_f077`

Primer `migrate`:

```text
Primer migrate : 0
```

Segundo `migrate`:

```text
No migrations to apply.
Segundo migrate: 0
```

La base descartable fue eliminada después de la prueba.

## CI remoto

GitHub Actions run #26:

`35822046560`

Commit:

`48278a7e0556dd9ea2cd01d9b6c164118b2391a6`

Jobs verdes:

- `lint`
- `django-check`
- `postgres-migrations`
- `tests-postgresql`
- `concurrency-postgresql`
- `postgres-privileges`
- `openapi-drift`

## Riesgos y bloqueos

No quedan bloqueos funcionales de F07.7.

La provisión real de Cloudflare R2, el dominio público y las credenciales pertenece a infraestructura/despliegue. Ningún secreto se versiona en el repositorio.

## Resultado final

F07.7 queda cerrada y satisface la precondición de media persistente requerida antes de continuar la integración productiva.
