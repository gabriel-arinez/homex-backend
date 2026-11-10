# HOMEX · Proforma Editorial Modular (decisiones aprobadas)

Documento de referencia permanente de FRONT SENIOR V. Fuente de diseño: proformas #578 y #590, capturas del visor, boceto visual y las cinco páginas de la Planilla Visual y Propuesta de Rediseño Proformas HOMEX (noviembre de 2026).

## Objetivos y jerarquía

Retícula tamaño carta fija. La lectura debe seguir: marca HOMEX y número/estado → cliente y condiciones → detalle técnico → precio → total y firmas. Los módulos comparten márgenes, columnas y espaciados. El generador PDF del backend es canónico para vista previa, descarga e impresión.

## Tres modos de presentación

1. Visual comercial: ítems con imagen real autorizada y especificaciones técnicas al lado. La foto respeta proporciones, no determina alturas excesivas y jamás hace que el texto caiga debajo de ella.
2. Compacto técnico: productos sin imagen, sin celda vacía ni cartel de imagen pendiente. Especificaciones a ancho completo, con subcolumnas únicamente si mejoran la lectura. Aplicable a licitaciones y muchos ítems.
3. Comparativo de alternativas excluyentes: una alternativa representa un precio y configuración independiente; no se suman alternativas. No inferir este modo a partir de nombres, descripciones o JSON técnico. Es imprescindible persistir, validar y exponer grupos/opciones en el dominio comercial y definir selección y totales antes de habilitarlo (no existe aún ese contrato en la rama base).

## Reglas visuales y comerciales

- Tabla con cuatro ejes fijos y numéricos: ÍTEM/CANTIDAD; DESCRIPCIÓN/ESPECIFICACIONES; PRECIO UNITARIO; IMPORTE.
- Repetir el encabezado en páginas sucesivas, evitar cortes inadecuados de ítems y desbordes de bordes.
- Composición adaptativa con y sin fotografía, con componentes, dimensiones y observaciones estructurados.
- Descuento de ítem y global solo si su importe es mayor que cero.
- Sin ajustes globales, mostrar únicamente TOTAL COTIZADO; no duplicar subtotal general.
- TOTAL_NEGOCIADO no se rotula como precio por unidad.
- Cabecera dual para cliente/destinatario y condiciones comerciales; se muestran los datos realmente persistidos.
- Cierre con observaciones registradas y dos firmas con espacio suficiente para escritura manual.
- La numeración del documento debe ser «Página X de Y»; tamaño carta físico y presentación monetaria BOB adecuada.
- No inventar garantías, vencimientos, personas, direcciones, cláusulas legales ni datos corporativos.
- Preservar cálculos, permisos, estados, contratos, snapshots históricos y auditoría.

## Criterios de aceptación

Probar fotografías con distintas proporciones, ítems sin imagen, documentos largos (28 ítems), cantidades decimales, modalidades de cálculo, descuentos positivos y cero, texto técnico extenso, condiciones largas, firmas, paginación, vista/descarga/impresión idénticas y visor accesible en móvil. La tercera modalidad no debe declararse terminada sin modelo de alternativas y pruebas económicas.

Implementación principal: apps/documentos/pdf.py (ReportLab) y src/modules/proformas/components/DocumentViewerModal.vue (PDF.js en frontend).
