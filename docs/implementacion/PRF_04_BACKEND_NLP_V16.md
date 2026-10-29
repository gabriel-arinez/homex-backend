# Integración candidata NLP V16

Base backend `b2d7ef45a8df7b9616abb417517763fe0859983d`.
Se fija homex-nlp 0.1.16 mediante wheel local, SHA256 y uv.lock. El adaptador
exige exactamente esa versión; mantiene RULES_ONLY, contrato 1.0 y PRF04_2.
Las variantes descriptivas sólo resuelven tipos ya existentes y activos; no se
crean códigos, catálogos, migraciones ni permisos. PR #42 permanece separado.

Verificar con `sha256sum --check vendor/homex_nlp-0.1.16.sha256`,
`uv sync --locked --extra dev --extra worker`, y las suites PRF-04/F08 sobre
PostgreSQL de pruebas dedicado. El total negociado sigue siendo pendiente:
la referencia unitaria del motor nunca se copia a precio_unitario efectivo.
El frontend debe exigir descuento cero confirmado y división exacta a centavos.

La comparación NLP mejora los guiones conocidos pero no aprueba su reemplazo:
el holdout conocido continúa 0/5 y conserva regresiones medidas. Esta rama
prepara una incorporación reproducible, no autoriza merge ni despliegue.

## Worker observado y procedimiento posterior

Se inspeccionó sin modificar `homex-prod-worker-1`, proyecto `homex-prod`, imagen
`homex/backend:d04-9ce7230`, ID
`sha256:af5a9c94a91cb8977bb166afa380425b41a415291fdcba2e73fe20eaa35c9359`.
Paquete instalado y adaptador dentro del contenedor esperan 0.1.0, mientras
origin/main espera 0.1.15. Es una imagen histórica, no el checkout main actual.
No atribuir a ese contenedor la revisión reciente del repositorio. La etiqueta
identifica la revisión de imagen; sus hashes se conservan en el expediente privado.

Después de homologar y autorizar una entrega: construir una imagen nueva desde
el commit backend aprobado y wheel fijado, verificar versión/hash dentro de la
imagen, ejecutar las regresiones aisladas, y reemplazar workers/API mediante el
procedimiento operativo de deploy. No ejecutar `pip install` dentro del worker
activo ni mezclar imágenes en la cola. Conservar rollback a la imagen previa.
No se realizó ese procedimiento en esta tarea.
