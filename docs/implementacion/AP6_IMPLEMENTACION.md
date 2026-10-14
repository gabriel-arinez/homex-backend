# AP6.0 — Implementación comercial y preparación AP3–AP5

## Alcance y fuentes

La implementación parte de las decisiones 6.0.1–6.0.20 del informe de cierre del 13-10-2026.
`homex_bd_final_v3.sql` se trató como referencia histórica; las migraciones Django nuevas son la
fuente operativa. No se desplegó ni modificó `homex-prod` y no se promovió D07 RC2.

## Matriz verificable

| Prioridad | Decisiones | Implementación | Evidencia |
|---|---|---|---|
| P0 | 6.0.1, 6.0.2, 6.0.3, 6.0.16 | Unidades `M2`, `BARRA`, `JUEGO`; cantidades/stock/movimientos `numeric(14,4)`; enteros salvo M2 | migraciones `catalogo.0008`, `proformas.0005/0006`, `movimientos_stock.0004`; tests AP6 |
| P0 | 6.0.6 | Nuevas líneas exclusivamente `PRECIO_UNITARIO`; precio y descuento explícitos; totales protegidos por PostgreSQL | `proformas.0006`, servicios y OpenAPI |
| P0 | 6.0.8, 6.0.10, 6.0.11 | Familias y variantes; unicidad de producto por proforma; familia pendiente hasta aprobación | constraint parcial, trigger de aprobación y API de familias |
| P0 | 6.0.13, 6.0.19 | OT única; catálogo resumido; detalle técnico sólo de muebles; acceso explícito `JEFE_TALLER` | permiso `taller.operar`, serializer OT y pruebas API |
| P0 | 6.0.14, 6.0.20 | Catálogo salta producción; mixto/mueble la requiere; cancelación conserva proforma aprobada y reversa única | transición/guards PostgreSQL y pruebas concurrentes |
| P1 | 6.0.4, 6.0.5, 6.0.9, 6.0.21 | Ficha flexible en un único `datos_tecnicos` JSONB, original y advertencias; admite “a elección” | `proformas.0009`, modelo/serializer y validación PostgreSQL |
| P1 | 6.0.7, 6.0.12, 6.0.17, 6.0.18 | Proformas separadas, sin servicios, sin maestro para muebles y sin importar NER | contrato API/importador y pruebas de regresión |
| P1 | AP3 | `BORRADOR`, `EN_REVISION`, `APROBADA`, `NO_CONCRETADA`; reapertura `NO_CONCRETADA → EN_REVISION`; legados aceptados sin renombrarlos | datos de catálogo, acciones y compatibilidad de transición |
| P1 | AP4–AP5 | clientes existentes; editor mixto; familia pendiente y características flexibles | OpenAPI y consumidor frontend generado |

## Preservación histórica

Se restauró el respaldo `homex-20261009T051913Z` en PostgreSQL aislado. Inventario previo: 0
productos, 1 proforma, 1 detalle, 0 movimientos, 0 pedidos. El detalle histórico era `PIEZA`, modo
`TOTAL_NEGOCIADO`, total Bs 1.800. Tras aplicar AP6 conservó exactamente modo y total. No había
registros `CAJA`; por ello no se ejecutó ni se infirió conversión CAJA→M2. `CAJA` permanece válido
para referencias históricas. Los reportes están en
`~/Descargas/ap6-preflight-20261013/`.

## Integridad y concurrencia

PostgreSQL bloquea proforma/producto durante aprobación, salida y reversa. Una venta decimal usa la
cantidad exacta; una única `REVERSA_VENTA` referencia su venta original. El pedido no puede forzar
cancelación si existen recibos emitidos o una entrega incompatible. La proforma aprobada sigue como
antecedente inmutable.

## Contratos y seguridad

El backend ya no sustituye el precio/descuento declarado por el vendedor al seleccionar catálogo.
`OrdenTrabajoSerializer` no expone precios ni totales y sólo incluye ficha técnica en muebles a
medida. `JEFE_TALLER` recibe `taller.operar`; los vendedores conservan el acceso operativo previsto.
HITL acepta únicamente precio unitario y nunca aprueba automáticamente la proforma.

## Límites honestos

- No se clasificaron `NA9118`/`NA9174` ni se inventaron SKU, equivalencias, precios o stock.
- NLP v1 continúa extrayendo una propuesta de un mueble; HITL organiza la propuesta validada en el
  JSON comercial único sin alterar el contrato externo.
- No se añadió edición posterior de especificaciones aprobadas ni servicios comerciales.
- La promoción/despliegue productivo y el piloto permanecen fuera de AP6.

## Correcciones de auditoría posteriores a la implementación inicial

- Migraciones nuevas `proformas.0007_ap6_unidades_redondeo` y
  `proformas.0008_ap6_caja_historica_stock`: la unidad de cada línea seleccionada
  debe coincidir exactamente con `Producto.unidad_stock`. Así, un zócalo en BARRA no puede
  descontarse como PIEZA; se evita cualquier conversión implícita de cantidades.
  La función preexistente `fn_proteger_clasificacion_producto` ya impide cambiar
  `unidad_stock`, incluso en productos sin movimientos; se verificó con una nueva prueba.
  Se descartó añadir un trigger duplicado.
- El bruto de cada línea se redondea a dos decimales en PostgreSQL y el subtotal se suma desde
  `total + descuento` de las líneas. El total de la proforma coincide con la suma de sus líneas,
  incluso para fracciones `M2` con precios de un céntimo. La escritura directa de
  `proformas_detalle.total` vuelve a calcular el importe.
- `EspecificacionMuebleSerializer` valida componentes del JSON comercial con nombre y tipos de atributos;
  las advertencias son textos. No se exige decidir colores marcados «a elección» antes de producir.
- Tanto el serializador de OT como su HTML controlan el acceso por rol. El jefe de taller recibe
  las especificaciones de los muebles a medida; el catálogo sólo aparece resumido y sin precios.
  El vendedor ve los ítems, no fichas técnicas reservadas al taller.
- `tests/integration/test_ap6_correcciones.py` cubre las reglas anteriores con Django y
  PostgreSQL. En el gate `postgres-migrations`, `scripts/ap6_legacy_caja_fixture.py` inserta,
  ANTES de AP6, un piso histórico con 5 CAJA, movimiento inicial y proforma
  `TOTAL_NEGOCIADO` de Bs 1.800; después de migrar verifica unidades, inventario, equivalencia
  histórica y totales. También registra movimientos de ajuste negativos y positivos en CAJA
  histórica, devolviendo el saldo a su valor original; los pisos nuevos continúan exigiendo M2. Este caso es un fixture sintético; no demuestra
  que el respaldo real contenga CAJA ni autoriza convertirla a M2.

## AP6.0.21 — JSONB técnico comercial único

La migración `proformas.0009_datos_tecnicos_unicos_ap6021` agrega `datos_tecnicos JSONB`, consolida
cada fila existente y después retira `schema_version`, `espesor`, `color_principal`,
`color_secundario`, `dimensiones`, `accesorios`, `componentes`, `texto_original` y `advertencias`.
La tabla queda formada por `id`, `proforma_detalle_id`, `tipo_mueble_id`, `datos_tecnicos` y
`observaciones`.

La transformación preserva los componentes y accesorios en sus claves homónimas, el texto como
`descripcion_original` y las advertencias como `advertencias`. Los campos antiguos que no tenían
una asociación demostrable con un componente se guardan bajo `caracteristicas_generales`; no se
inventan relaciones. Los atributos de cada componente permanecen abiertos, mientras PostgreSQL y
DRF exigen un objeto raíz, nombres no vacíos en componentes y listas de texto válidas para
accesorios y advertencias. No existe `schema_version` comercial, ni como columna ni dentro del JSON.

HITL copia el objeto revisado y conserva además la transcripción ASR en `descripcion_original`.
`ItemIA`, `ItemHumano` y `resultado_raw` continúan como evidencia inmutable del contrato NLP v1.
Las OT exponen el objeto completo sólo al jefe de taller; el vendedor sigue recibiendo la ficha como
`null`. La protección PostgreSQL de proformas aprobadas continúa cubriendo detalle y especificación.

El diagnóstico previo quedó en `~/Descargas/ap6021-diagnostico-20261014/`. `homex_dev` tenía 0
especificaciones, 6 proformas, 10 detalles, 3 pedidos y 3 OT; se generó el respaldo recuperable
`homex_dev_pre_ap6021.dump` con SHA-256
`6bb0497ebbd386f6d94fb6657121f48fecd14586c601e861d1b97d3ce5ad3404`. No se consultó ni modificó
el contenedor `homex-prod`. La preservación de una fila sintética con todos los campos heredados se
verifica automáticamente en `test_ap6021_migracion.py`; la actualización de la copia de desarrollo
se ensaya en PostgreSQL aislado.

Validación local AP6.0.21: migración desde cero y segunda ejecución no-op; actualización de la copia
aislada `homex_dev` conservando 6 proformas, 10 detalles, 3 pedidos y 3 OT; 213 pruebas globales,
7 pruebas focalizadas de migración/JSON y 12 pruebas de concurrencia. `check`, ausencia de
migraciones pendientes y OpenAPI sin drift también quedaron verdes localmente.


## AP6.0.21 — Correcciones posteriores de auditoría (migración segura y consistencia)

- La migración `0009` ya estaba integrada y **no se reescribió**. Su
  `RunPython` actualiza cada ficha, mientras que el trigger histórico
  `trg_bloquear_especificacion_aprobada` rechaza actualizaciones de fichas
  vinculadas a proformas `APROBADA`. Una BD que todavía esté en
  `proformas.0008` **con fichas aprobadas** no debe ejecutar `migrate`
  directamente para AP6.0.21: utilice
  `scripts/ap6021_upgrade_aprobadas.py` después de backup PostgreSQL real,
  checksum SHA-256 y ensayo de restore en copia aislada. El script exige
  coincidencia del nombre de BD y una frase de confirmación; desactiva sólo
  ese trigger dentro de una transacción con bloqueo exclusivo PostgreSQL,
  aplica `0009` y `0010`, verifica igualdad íntegra de fichas migradas y
  restaura la protección antes del commit. Si algo falla, PostgreSQL revierte
  DDL, migraciones y datos, incluido el estado del trigger. No se ejecutó
  este comando sobre producción.
- La nueva `0010_ap6021_validacion_y_rollback_seguro` comprueba en PostgreSQL
  los tipos de material, espesor, color, acabado y dimensiones cuando existen
  (texto/objeto, sin listas cerradas ni obligatoriedad universal).
  Los dos serializadores DRF comparten la misma validación.
- `0010` impide explícitamente revertir hacia `0009` y `0008` desde
  Django, ya que eliminar `datos_tecnicos` perdería información. El rollback
  autorizado es **restaurar backup recuperable, medios asociados y código
  compatible**, no `migrate proformas 0008`. Para bases que ya aplicaron
  `0009`, ejecutar `0010` normalmente.
- El backend HITL compara atributos técnicos globales y accesorios con
  `ItemHumano`: proyecta valores humanos revisados a
  `caracteristicas_generales` cuando no están presentes, rechaza
  contradicciones y conserva las características específicas de cada
  componente sin atribuciones supuestas. Conserva la transcripción
  inmutable y las claves técnicas abiertas.
- El documento de proforma ahora incluye el JSON técnico de cada mueble a
  medida. La OT continúa diferenciando permisos y sin imprimir precios.
- CI `postgres-migrations` incorpora **dos fichas heredadas** (una
  `APROBADA`, otra `BORRADOR`), crea backup PostgreSQL 17 previo, ejecuta
  el upgrade transaccional y verifica cada campo y el trigger restablecido.
  Las pruebas PostgreSQL comprueban rechazo de tipos inválidos, atomicidad
  HITL e inmutabilidad. Los recuentos y resultados definitivos constan
  en GitHub Actions del PR correctivo.
- Los ensayos en CI son de bases descartables; no sustituyen el inventario
  ni el restore del entorno de destino. La candidata D07 RC2 y
  `homex-prod` permanecen fuera de esta corrección.
