# PRF-03 — Especificación definitiva BACKEND: configurador integral de muebles a pedido (HOMEX)

**Estado funcional:** PRF-03.1–PRF-03.6 APROBADOS por el usuario (18-10-2026). **Estado de ejecución:** documento de implementación; no acredita código PRF-03 ni pruebas ejecutadas.
**Baseline contrastada:** backend main a6eee1180b345a3b4b2ebf100a5682cf2efddc4f; frontend main 5e5975c18a28ac7214395f4144a761cea8f4bf85. Revalidar ambos HEAD y PRF-02 antes de programar.
**Documento par obligatorio:** homex-frontend/docs/implementacion/PRF_03_FRONTEND.md.
**Referencias:** PRF_01_BACKEND.md, PRF_02_BACKEND.md, AP6_IMPLEMENTACION.md, config/urls.py, apps/catalogo/{models.py,api/views.py,api/serializers.py}, apps/proformas/{models.py,validacion_tecnica.py,api/serializers.py,api/views.py,services.py}, docs/openapi.yaml y pruebas reales.
**Fuente de casos:** corpus proporcionado por el usuario «PROFORMAS(2).txt»; no consta como archivo versionado en este repositorio. Los casos y cantidades de este documento provienen de ese material, no de fixtures inventados.

> Implementar lo aprobado, no diseñar de nuevo el producto. No crear una segunda ficha técnica, otra proforma, otro motor de precios o una jerarquía relacional de piezas. La autoridad comercial continúa en backend/PostgreSQL. PRF-03 se ocupa de la captura manual; voz, NLP y asistencia posterior son PRF-04; rediseño documental es PRF-06.

## 0. Baseline comprobada y brechas

- Proforma -> DetalleProforma -> EspecificacionMueble: un detalle MUEBLE_MEDIDA y una ficha OneToOne; datos_tecnicos JSONField, tipo_mueble FK nullable y observaciones TextField.
- DetalleProforma tiene nombre, descripcion, cantidad, unidad, modo_calculo, precio_unitario, descuento, total. Los muebles nuevos no apuntan a Producto ni FamiliaProducto.
- validar_datos_tecnicos valida raíz objeto, componentes lista de mapas con nombre no vacío, atributos básicos material/espesor/color/acabado/dimensiones texto u objeto, caracteristicas_generales objeto, accesorios/advertencias listas de textos no vacíos; rechaza schema_version. NO impone todavía conjuntos, vínculos, límites ni atributos nuevos.
- ValorCatalogo y ConceptoCatalogo son catálogos reales con unicidad (concepto, codigo). GET /api/v1/catalogo/opciones/?concepto=TIPO_MUEBLE es de solo lectura bajo EsVendedor; NO ofrece alta de tipo por vendedor. Producto/Familia usan EsAdministradorComercial para mutaciones y deben continuar así.
- POST /api/v1/proformas/integral/ y PUT /api/v1/proformas/{id}/integral/ son los mecanismos comerciales existentes. El editor frontend todavía separa formulario comercial de EspecificacionForm y muestra otros atributos como JSON; la nueva experiencia completa corresponde a PRF-03.
- PRF-02 ya aportó cambios al catálogo, editor y OpenAPI respecto de su baseline documental. No presuponer que cualquier integración futura esté aceptada o que el trabajo en main permanezca estático.

## 1. Invariantes y alcance

1. **Mueble a pedido = una línea comercial + una ficha técnica**; conjuntos, componentes y accesorios NO generan productos, SKU, ítems comercializables ni movimientos de stock.
2. Reutilizar EspecificacionMueble y el JSONB comercial único; no crear tablas de conjunto/componente ni un segundo formato de especificación. No incluir «schema_version».
3. Mantener el contrato técnico abierto: campos desconocidos, antiguos y atributos específicos se leen/escriben sin borrarse; no exigir migración retrospectiva ni completar campos inexistentes.
4. La modalidad manual funciona sin micrófono ni NLP; descripcion_original se preserva cuando exista, pero no se introduce como otro campo obligatorio del vendedor ni se sobrescribe.
5. Conservar permisos, ownership, estados, bloqueo de ficha/proforma aprobada, control concurrente revision_esperada, clave_idempotencia y transaccionalidad del integral.
6. Muebles a pedido: PIEZA/JUEGO con cantidad comercial positiva entera; precio unitario de línea nueva > 0; descuento monetario de línea >=0 y <= bruto; USD sin conversión implícita. Preservar históricos TOTAL_NEGOCIADO.
7. La ficha técnica no reserva stock, no crea pedidos, venta, movimientos ni OT por edición o guardado de borrador.
8. Cambios de PRF-03 deben limitarse a proformas/especificación y catálogo de atributos/tipos estrictamente necesario; no alterar NLP, audio, clientes, inventario, documentos ni maestros de Producto.

## 2. PRF-03.1 — Entrada, escritura y persistencia

- El frontend abre un configurador integral de página completa para CREAR/EDITAR/DUPLICAR MUEBLE_MEDIDA. Backend NO recibe la ficha al entrar, cambiar de sección o confirmar localmente.
- Cuando el vendedor guarda la proforma por acción expresa, la operación integral mantiene simultáneamente DetalleProforma y EspecificacionMueble. La edición conserva ID de detalle y de especificación; no borrar/recrear ficha durante actualización.
- Una copia de mueble utiliza objeto técnico clonado independientemente; la identificación comercial de la línea recién añadida se asigna en el guardado integral. Nunca reutilizar ID de detalle original en la nueva copia.
- Una lectura de fichas aprobadas sigue protegida. Una especificación no se asocia a SILLA/PISO_FLOTANTE/OTRO.
- Atributos/colecciones visuales opcionales no deben originar escrituras automáticas o recalcular precio/total técnico.

## 3. PRF-03.2 — Tipos de mueble y catálogo de atributos

### 3.1 Tipo de mueble: creación contextual y privilegios acotados

Crear una **operación específica** (POST /api/v1/catalogo/tipos-mueble/) y documentarla en OpenAPI. Permiso EsVendedor, verificación de autenticación y autorización en servidor, independiente de comercial.administrar. Acepta exclusivamente nombre de un ValorCatalogo del concepto fijo TIPO_MUEBLE; NO acepta concepto_id, activo, codigo arbitrario, actor, cambios de permisos, campos extras o modificaciones de otros conceptos.

- Validar nombre real, trimmed, longitud conforme a ValorCatalogo.nombre y ausencia de caracteres de control. Normalizar para comparación: espacios repetidos, mayúsculas/minúsculas, tildes y signos de separación equivalentes; mantener nombre presentado por vendedor después de sanitizarlo.
- Buscar equivalencia exacta normalizada y detectar nombres muy similares; si coincide, devolver 409 y el tipo existente apto para seleccionarse; cuando solo sea parecido, sugerir coincidencias para decisión humana, sin afirmar equivalencia ni fusionarlas silenciosamente.
- Generar un codigo de tipo determinista y único dentro de TIPO_MUEBLE, controlado por servidor (slug canónico y manejo de colisiones). Reforzar atomicidad, integridad única (concepto,codigo), recuperación segura de IntegrityError y prueba de dos altas concurrentes. No depender exclusivamente de SELECT previo ni confiar en validación Vue.
- Guardar auditoría created_by/updated_by con actor y devolver id/nombre/codigo del tipo creado. El frontend lo selecciona tras POST exitoso; crear tipo NO guarda la proforma.
- No habilitar POST/PATCH/DELETE genéricos sobre /catalogo/opciones, /catalogo/productos ni /catalogo/familias a vendedores. Administración general fuera de PRF-03.

### 3.2 Diccionario técnico de campos dinámicos

No convertir cada valor particular («PVC fusionado», «llave simultánea») en una opción global. El catálogo registra **definiciones de campo**: código estable, nombre visual, grupo, tipo de entrada, términos de búsqueda/sinónimos, ámbito sugerido (mueble/componente) y estado activo.

Diseño mínimo preferido: reutilizar ConceptoCatalogo + ValorCatalogo mediante un concepto específico como ATRIBUTO_MUEBLE, y agregar metadatos exclusivos para esos valores en una relación anexa si realmente son necesarios (sin modificar semántica universal de ValorCatalogo); equivalente aislado de catálogo está permitido si resulta claramente menor y se justifica. No usar claves dinámicas descontroladas como columnas ni agregar permisos genéricos de creación a vendedores.

Proveer una API de lectura autenticada (GET /api/v1/catalogo/atributos-mueble/) con búsqueda servidor o catálogo acotado cacheable, resultados ordenados alfabéticamente, búsqueda normalizada por nombre/sinónimos y grupos/sugerencias para componentes; incluir metadatos de límites operativos para evitar números inconsistentes en UI. Especificar forma y errores en OpenAPI y regenerar cliente TS.

Semilla idempotente y trazable de términos respaldados por el corpus (no valores inventados): Configuración/Forma, Lado, Diámetro, Alto, Largo, Cantidad de cajones, Espesor de tapa, Espesor de laterales, Material, Revestimiento, Tapacanto, Fijación, Paso de cables, Tratamiento, Acabado, Sistema de cierre, Apertura de cajones, Deslizamiento/Rieles, Número de puertas, Repisas, Tapizado, Relleno, Posición/Orientación, etc. Términos adicionales sectoriales pueden incorporarse claramente identificados como ampliación; no presentar datos de ejemplo como vocabulario certificado del corpus. No implementar aún una pantalla de administración general.

Cuando un vendedor añade un atributo personalizado no catalogado, su nombre/valor se conserva en la ficha concreta, NO se inserta en el diccionario global automáticamente.

### 3.3 Contrato público común a frontend y backend (decisión técnica de implementación)

Fijar en OpenAPI las rutas siguientes, registradas en config/urls.py sin abrir escritura genérica de catálogos:

1. **GET /api/v1/catalogo/atributos-mueble/** (EsVendedor): respuesta objeto con `limites: {max_conjuntos: 10, max_componentes: 40}` y `atributos: [{id, codigo, nombre, grupo, tipo_entrada, ambitos, sinonimos}]`, orden alfabético por nombre. Solo atributos activos para nuevas selecciones. `tipo_entrada` admite al menos texto/entero/numero_unidad; `ambitos` contiene mueble y/o componente. Búsqueda opcional mediante `search` normalizado, manteniendo el mismo contrato de respuesta. Las fichas históricas conservan snapshots aunque el atributo haya sido desactivado.
2. **POST /api/v1/catalogo/tipos-mueble/** (EsVendedor): petición exacta `{nombre: string}`, respuesta 201 `{id, codigo, nombre}`. Coincidencia normalizada existente: 409 con `{codigo: "tipo_duplicado", existente: {id, codigo, nombre}}`. 400 para nombre inválido, 401/403 para no autorizados. El servidor define concepto y código sin aceptar parámetros de otros catálogos. Ante similitud NO exacta, el selector muestra coincidencias en la consulta y solicita decisión del vendedor; no suponer equivalencia ni crear clones silenciosos.
3. El modelo de metadatos para ATRIBUTO_MUEBLE debe estar separado del ValorCatalogo base: relación OneToOne a ValorCatalogo con grupo, tipo_entrada, ambitos y sinonimos; los elementos siguen perteneciendo al concepto ATRIBUTO_MUEBLE. Se aplican migración aditiva y siembra idempotente sin cambiar catálogos históricos.
4. Los códigos de atributos se persistirán dentro de datos_tecnicos junto a etiqueta snapshot y valor ingresado; NO FK por componente ni validación que exija que una definición histórica permanezca activa.
5. Frontend consume límites del GET al estar disponible; backend valida siempre los límites por sí mismo. Si el diccionario no puede cargarse, el editor mantiene el borrador y permite atributos libres sin simular un catálogo cargado. Validar fallos y conservar datos.

Estos nombres de rutas y formas de respuesta son el contrato objetivo de PRF-03 y sustituyen las menciones anteriores a «ruta sugerida»; solo un conflicto real verificado con rutas preexistentes justificaría documentar una modificación sincronizada de ambos repositorios.

## 4. PRF-03.3 — Forma técnica JSON interoperable

Definir una estructura canónica documentada y **aditiva**, sin romper validaciones actuales ni exigir convertir fichas heredadas. El siguiente objeto es ilustrativo de las claves nuevas, NO corresponde a una API existente:

~~~json
{
  "caracteristicas_generales": {
    "dimensiones": {
      "alto": {"valor": "73", "unidad": "cm"},
      "lado_1": {"valor": "140", "unidad": "cm"},
      "lado_2": {"valor": "140", "unidad": "cm"}
    },
    "atributos": [
      {"codigo": "CONFIGURACION_FORMA", "nombre": "Configuración / Forma", "valor": "En L"}
    ]
  },
  "conjuntos": [
    {"uid": "escritorio", "nombre": "Escritorio"},
    {"uid": "cajonera", "nombre": "Cajonera rodante"}
  ],
  "componentes": [
    {
      "uid": "meson", "conjunto_uid": "escritorio", "nombre": "Tapa superior / Mesón",
      "material": "Madera aglomerada MDP", "espesor": "25 mm",
      "atributos": [
        {"codigo": "REVESTIMIENTO", "nombre": "Revestimiento", "valor": "Lámina de melamina"},
        {"codigo": "TAPACANTO", "nombre": "Tapacanto", "valor": "PVC con fusión caliente"}
      ]
    },
    {
      "uid": "cajonera_rodante", "conjunto_uid": "cajonera", "nombre": "Cajonera rodante",
      "cantidad_interna": 1,
      "material": "Madera aglomerada MDP",
      "dimensiones": "33x40x63 cm; orden de ejes por confirmar",
      "atributos": [
        {"codigo": "CANTIDAD_CAJONES", "nombre": "Cantidad de cajones", "valor": "4"}
      ]
    }
  ],
  "accesorios": ["Zapatas regulables en formato redondo"],
  "advertencias": []
}
~~~

- Los UID de conjuntos/componentes son identificadores técnicos internos estables en la ficha; usar valores opacos y únicos por ficha al crear, NO basarse en nombre/posición. Este ejemplo abreviado usa etiquetas explicativas; en producción preferir UUID. El vínculo conjunto_uid es opcional; ningún sub-conjunto ni ciclos.
- Grupos solo organizativos: de 0 a 10 conjuntos; componentes de 0 a 40 **por mueble**, sumados entre agrupados y no agrupados. Límites configurables en una única fuente backend, reflejados al frontend; valores iniciales aprobados 10/40. Nunca cambiar el precio por agrupar.
- Si existe un conjunto en una ficha nueva/actualizada, debe tener nombre y al menos un componente referenciado. No crear otro mientras haya uno vacío en UI; al guardar tampoco aceptar conjuntos huérfanos. Las fichas históricas sin «conjuntos» continúan válidas.
- Cada componente requiere nombre no vacío; cantidad_interna opcional, entero positivo si se proporciona; NO equivale a DetalleProforma.cantidad. Diferenciar piezas por mueble de la cantidad de muebles vendidos. Cero o negativos inválidos.
- Dimensiones de raíz son sugerencias opcionales: ancho, alto, profundidad, y medidas añadibles (lado 1, lado 2, diámetro, altura total). Guardar unidad por valor cuando se conozca; conservar texto ambiguo sin conversiones silenciosas. Dimensiones de componentes independientes; el campo heredado componentes[].dimensiones sigue admitiendo str/dict.
- Atributos técnicos de ámbito mueble y componente son lista explícita de campos seleccionados con nombre, valor y código cuando corresponda. Validar lista/mapa de forma segura, identificación de duplicados exactos en el mismo ámbito, tipos/longitudes razonables y valores no vacíos al confirmar. Las etiquetas originales permanecen para visualizar referencias de catálogo inactivadas/renombradas.
- No inferir color por pieza a partir de un color global, ejes desde «33x40x63», unidad desde «60,50» ni alternativa de cierre. Los datos dudosos van a observaciones o advertencias ya existentes.
- Mantener los campos básicos preexistentes (nombre, material, espesor, color, acabado, dimensiones); solo añadir nuevos campos si el contrato lo necesita y preservando cualquier clave extra o anidación histórica.

### Compatibilidad y preservación

La validación **distinguirá formas nuevas de legado sin exigir migraciones destructivas**. Si una ficha no contiene «conjuntos», «uid», «atributos» o «cantidad_interna», sigue siendo válida. Si sí los contiene, deben validarse límites, vínculos, unicidad de uid y coherencia. Cuidado con el no-op de líneas aprobadas y con el parche de una sola propiedad: conservar todo el resto del JSON profundo, no reconstruir únicamente claves conocidas.

Nunca borrar ni trasladar automáticamente «descripcion_original», «advertencias», «accesorios» o «caracteristicas_generales». Rechazar schema_version, conforme al contrato actual. Prevenir pérdidas al reabrir una ficha vieja de forma textual u objeto JSON; comprobar roundtrip semántico.

## 5. PRF-03.4 — Accesorios, pendientes y observaciones

- Conservar «accesorios» como lista de strings **no vacíos**: cada accesorio se edita visualmente por separado, pero serializa al mismo tipo existente. La cantidad o destino explícito puede incluirse en texto; no crear productos, subprecios ni una tabla adicional de accesorios.
- Un solo accesorio sin completar en UI; impedir enviar elementos vacíos al servidor. No duplicar automáticamente un herraje ya descrito en el componente.
- «observaciones» sigue en EspecificacionMueble.observaciones, libre; la información dudosa de la muestra no autoriza rellenar medidas ni opciones. «advertencias» es lista histórica distinta: mostrar y preservar sus entradas, sin un segundo campo genérico obligatorio ni sobreescritura al editar observaciones.
- «descripcion_original» de capturas existentes sobrevive intacta; PRF-03 manual no exige ese texto. NLP/voz sigue fuera de alcance.

## 6. PRF-03.5 — Validación comercial, integral y duplicación

- Validaciones básicas: nombre de línea obligatorio, cantidad comercial positiva entera PIEZA/JUEGO, precio nuevo positivo, descuento total de línea entre 0 e importe bruto, unidad permitida y ninguna familia/producto referenciados por mueble.
- La ficha puede tener medidas, color, materiales y características desconocidos o «A elección»; no imponer requisitos técnicos inventados ni bloquearla solo por observaciones o advertencias. No exigir componentes por defecto si la proforma real solo documenta el conjunto; si hay componentes añadidos, no pueden estar vacíos.
- Las reglas de conjuntos/40 componentes se verifican en servidor incluso al escribir por la API, manteniendo histórico legítimo bajo edición sin pérdida; ante legado que exceda nuevos topes, no truncar ni reescribir: devolver conflicto/validación explícita solo ante edición estructural incompatible y definir prueba específica.
- Guardado comercial exclusivamente integral por petición explícita. No segundo endpoint de persistencia de borrador técnico en cada cambio.
- El frontend compara **representación comercial + técnica completa** al duplicar. Una modificación de espesor/material/atributos/conjuntos/cantidades internas es una diferencia real aun si nombre, precio y cantidad son iguales. Si idéntico, ofrecer sumar cantidad original solo con confirmación expresa; backend conserva integridad e IDs y no hace fusiones implícitas.
- La lectura/edición conserva observaciones y atributos desconocidos, y respetará estados aprobados, ownership, clave_idempotencia, revision_esperada, errores 400/403/404/409, rollback ante error y no duplicación de ficha.

## 7. Matriz de pruebas obligatorias PRF-03.6

| Grupo | Escenarios mínimos | Nivel |
|---|---|---|
| Contrato | JSON legado sin conjuntos; nuevo con conjuntos; claves desconocidas; sin schema_version | unit/DRF/PostgreSQL |
| Límites | 10 grupos/40 piezas válido; 11/41 inválido; suma entre grupos; grupo vacío/referencia ajena/uid repetido | unit/API |
| Atributos | catálogo alfabético, sinónimos, nombres personalizados, snapshot, inactivos, no pérdida | API |
| Permisos | vendedor lee y crea exclusivamente TIPO_MUEBLE; no modifica otros conceptos/maestros; anónimo 401/403 | API |
| Concurrencia | dos altas equivalentes simultáneas, código único, 409 con coincidencia, sin clones | PostgreSQL |
| Revisión | un mueble = una línea + una ficha; crear, editar, recuperar, duplicar con dato técnico diferente | integral/API |
| Comercial | PIEZA/JUEGO, precio/descuento/cantidad, USD, histórico TOTAL_NEGOCIADO, aprobadas solo lectura | API/DB |
| Fallos | 400/409, retry idempotente, rollback íntegro, preservación del borrador local coordinada con frontend | integración |
| No regresión | SILLA/PISO_FLOTANTE/OTRO, familias/SKU PRF-02, stock, pedidos, OT, NLP histórico, PDF | suites existentes |
| Corpus | velador 2 cajones; escritorio en L/cajonera; mesa redonda reuniones; sillones modulares; vitrina tipo 6 | fixtures + E2E |

**Datos verificados del corpus (no inferir el resto):**
- Velador 2 cajones: 6 PIEZA, 0,45 m ancho/profundidad, 0,60 m alto, melamina 18 mm, dos cajones con rieles telescópicos, Bs 750 unitario / Bs 4.500 total.
- Escritorio en L con cajonera: 2 PIEZA, 140x140 cm, alto 73 cm, MDP 25 mm tapa y 18 mm paneles, cajonera 33x40x63 cm, cuatro cajones, Bs 2.500 / Bs 5.000. «Profundidad en mesada en 60,50» y alternativas de cerradura se conservan ambiguas.
- Mesa sala de reuniones: diámetro 2,00 m, altura 0,75 m, caja eléctrica con dos USB/dos HDMI/dos tomacorrientes, topes goma, 2 PIEZA, Bs 7.300 / Bs 14.600.
- Sillones modulares: 1 JUEGO, 2 laterales + 2 centrales, 6 almohadones 0,45x0,45 m, Bs 12.000.
- Vitrina tipo 6: 8 PIEZA, 3,40x0,60x2,30 m, vidrio templado 8 mm, Bs 29.800 / Bs 238.400.

Comprobar con el corpus literal antes de convertir casos a fixtures. No atribuir a la misma pieza valores que la fuente solo sitúa en el conjunto.

## 8. Entrega y calidad de implementación

1. Inspeccionar HEAD actuales de ambos repositorios, migraciones existentes, endpoints, contrato y código PRF-02 antes de tocar código. No reescribir migraciones antiguas ni suprimir pruebas.
2. Diseñar en conjunto el contrato de atributos/tipo de mueble y estructura JSON; migraciones únicamente **aditivas y justificadas** para catálogo/metadatos, no para convertir EspecificacionMueble en tablas de piezas.
3. Actualizar modelos/serializers/vistas/servicios/autorización PostgreSQL necesarios; schema OpenAPI y cliente TypeScript regenerado en frontend. Implementar frontend siguiendo PRF_03_FRONTEND.md.
4. Pruebas PostgreSQL reales, migración limpia y compatibilidad, formato/lint/check/schema, CI y E2E de cinco casos, evidencia de pruebas de permisos y concurrencia. No afirmar éxito sin ejecuciones.
5. Entregar diff, commits, PRs, riesgos residuales, pruebas ejecutadas con resultados y comandos exactos de verificación local. No declarar PRF-03 completada hasta auditoría independiente.

## 9. Decisiones técnicas de implementación, NO cambios funcionales

- La clave nueva «conjuntos» y UID locales formalizan las agrupaciones ya aprobadas, sin alterar estructura comercial.
- El concepto ATRIBUTO_MUEBLE con metadatos estrechos aprovecha catálogos existentes; se permite alternativa igual de acotada justificada por inspección real. No habilita administración general.
- Un mueble puede no tener componentes documentados; la condición aprobada es no aceptar *componentes añadidos vacíos*, no inventar partes.
- La comparación de duplicación debe incluir la ficha completa, corrigiendo el riesgo del editor actual, que compara sobre todo datos comerciales.

**Resultado exigido:** captura y persistencia manual de especificaciones reales, sin pérdida, sin falsas inferencias, con catálogos acotados y sin regresión comercial.
