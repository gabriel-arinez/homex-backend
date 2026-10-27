# Consumo NLP 0.1.15 — voz confiable

Base backend #39 / 7ac385d115b0124dfc7131b17fe005ae3684d608.
Fuente NLP #33 / 9fda0f515661e35ce0e71e2a3ac38b5f699472fc.
Contrato 1.0, PRF04_2, ruedas/wheels históricos y revisiones inmutables conservados.

La proyección compara materiales sin distinguir capitalización ni el alias
melamine/melamina; no crea conflictos por repetición equivalente. Conserva el
primer literal para compatibilidad histórica, y sigue absteniéndose en valores
realmente diferentes. Proyecta colores normalizados tipados (no-gal → nogal).

Las variantes de tipo se resuelven contra filas activas reales de TIPO_MUEBLE:
escritorios/en L/escritor ejecutivo → Escritorio; mesas de reunión → Mesa de
reunión; gabeteros/gaveteros → Gavetero. Se exige un único resultado de BD;
no se fijan IDs. El catálogo inicial sólo contiene Mesa de reunión, Estante,
Escritorio, Credenza, Archivero y Gavetero. Velador/atril/recepción permanecen
pendientes. No se inventa equivalencia para cajonera móvil ni nuevas categorías.

Los precios inciertos quedan vacíos con INVALID_PRICE; el vendedor debe
introducir y confirmar el importe. TOTAL_NEGOCIADO sigue sin autocompletar
unitario. Capturas 3/4/5 se verifican por replay: pieza desconocida no recibe
espesor; ancho sin unidad no se completa desde alto; rectificación exige revisión.

## Laboratorio adicional

Recursos nuevos: PostgreSQL 127.0.0.1:25434, Redis 127.0.0.1:26381,
DB homex_voice_next, API 127.0.0.1:28002, frontend de integración 4174.
No reutilizar bases/colas de v14 ni voice-fixes. Credenciales, transcripciones,
matriz por captura y resultados privados viven exclusivamente en
~/Descargas/HOMEX_VOICE_NEXT_20261027/; lab.env tiene modo 0600.

Para reproducir sobre estos recursos aislados: cargar lab.env, ejecutar
`uv sync --locked --extra dev --extra worker`; pruebas con
`DJANGO_SETTINGS_MODULE=config.settings.test uv run --locked --extra dev --extra worker pytest`.
`manage.py check`, `makemigrations --check --dry-run` y `spectacular --validate`
no requieren cambios de migración/contrato. Comparar OpenAPI exportado con el
snapshot versionado. Verificar `sha256sum --check vendor/homex_nlp-0.1.15.sha256`.

Para E2E, usar settings.integration, migrar exclusivamente homex_voice_next,
sembrar con el script frontend seed-fe08-backend.py y arrancar API/worker/beat
con broker 26381/0. Generar WAV TTS con generar_audio_sintetico_prf04.py. Frontend:
HOMEX_INTEGRATION_API_URL=http://127.0.0.1:28002 y HOMEX_PRF04_AUDIO apuntando
al WAV sintético. El E2E guarda/relee una proforma y una RevisionAsistida;
no acredita voz humana nueva ni GOLD. Audio temporal eliminado y outbox publicado
sin errores se verifican en integration-db.json privado.

## Límites de evidencia

25 transcripciones reales se reproducen contra el motor y la proyección; no
se modifican capturas históricas. El precio de 19/20 sigue sin referencia humana:
no afirmar que era 8500. Errores ASR, espesores sin pieza, categorías ausentes y
geometría L no especificada requieren vendedor. Component no soporta árbol de
padre-hijo; no se inventa su representación. Los detalles se conservan también
en descripcion_original. No se calcula WER ni se entrena con el piloto.
