# F09.1 — Storage productivo configurable y despliegue privado

## Estado

**CERRADA.** Implementación funcional de la alineación arquitectónica aprobada el 30-09-2026.

## Decisión

La release inicial usa:

```text
HOMEX_MEDIA_STORAGE=filesystem
HOMEX_MEDIA_ROOT=/var/lib/homex/media
HOMEX_MEDIA_URL=/media/
```

`homex-deploy` es responsable de montar un directorio persistente del host en esa ruta y de
servirlo mediante Nginx.

S3/R2 permanece disponible con:

```text
HOMEX_MEDIA_STORAGE=s3
```

y conserva el contrato F07.7.

## HTTPS

`HOMEX_HTTPS_ENABLED=0` es válido para la topología inicial de red privada cifrada. Si deploy
entrega posteriormente un hostname HTTPS real, se activa con `HOMEX_HTTPS_ENABLED=1`.

No se fuerza un redirect HTTPS que rompa el acceso privado por IP/ruta interna.

## Base de datos

**No hay migraciones.** Modelos, columnas, keys y relaciones permanecen idénticos.

PostgreSQL continúa almacenando únicamente rutas/keys lógicas y metadatos.

## Compatibilidad

- endpoints de media: sin cambios;
- prefijos `productos/` y `proformas/`: sin cambios;
- WebP 320/640/1280: sin cambios;
- permisos de mutación: sin cambios;
- frontend: no distingue filesystem de S3.

## Gates de fase

- producción filesystem falla claramente si falta `HOMEX_MEDIA_ROOT`;
- filesystem no exige secretos R2;
- `HOMEX_MEDIA_ROOT` debe ser absoluto;
- storage desconocido falla;
- S3 conserva validación del bucket y secretos;
- HTTPS puede habilitarse explícitamente;
- OpenAPI no expone rutas físicas ni secretos;
- `makemigrations --check --dry-run` debe permanecer sin cambios.


## Evidencia remota de cierre

Commit funcional final: `7ca7ce85dceea8e4c9c7a852a4ec787af9b958c7`.

GitHub Actions CI run `36796486513`: **success**.

Jobs verdes:

- `lint`;
- `django-check`;
- `tests-postgresql`;
- `postgres-migrations`;
- `postgres-privileges`;
- `concurrency-postgresql`;
- `worker-smoke`;
- `f08-real-integration`;
- `openapi-drift`;
- `f09-frontend-integration`.

`makemigrations --check --dry-run` confirmó que F09.1 no introduce migraciones ni cambios de
esquema.

## Resultado

Backend queda preparado para D03:

- filesystem es el storage productivo inicial;
- S3/R2 permanece como alternativa;
- HTTPS es configurable según la topología real;
- modelos y OpenAPI mantienen compatibilidad.
