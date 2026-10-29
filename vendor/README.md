# Artefactos privados fijados

`homex_nlp-0.1.0-py3-none-any.whl` es el artefacto distribuible aprobado por F06 del repositorio
`homex-nlp` y consumido por F08.0.

- Paquete: `homex-nlp==0.1.0`
- Contrato: `schema_version == "1.0"`
- SHA-256: `cfacc3a987f6158f43934cb64304fa50ea3e577cfa576f3db1e6d2a9576d19e6`
- Rama canónica verificada: `homex-nlp/main`
- Commit canónico observado al integrar: `b5fe292` (`Merge F00-F06: HOMEX NLP backend-ready`)

El hash del wheel en `uv.lock` es la autoridad reproducible. No sustituir el archivo conservando el
mismo nombre; una nueva versión o build exige actualizar versión, hash, contrato y pruebas de
consumidor.


## Paquete operativo PRF-04 — 0.1.2

- Paquete: `homex-nlp==0.1.2`
- Wheel: `homex_nlp-0.1.2-py3-none-any.whl`
- SHA-256: `d78210bf0aed2553e496064592b046ca9c0aa3ff7342e50af9461a9f07451d9e`
- Contrato: `schema_version == "1.0"`
- Motor: `RULES_ONLY`, `prf04-rules-v3`
- Proyección: `PRF04_2`

Los artefactos anteriores permanecen conservados
para trazabilidad histórica. El wheel operativo
se selecciona mediante `pyproject.toml` y `uv.lock`.

## Paquete operativo PRF-04 — 0.1.3

- Paquete: `homex-nlp==0.1.3`
- Wheel: `homex_nlp-0.1.3-py3-none-any.whl`
- SHA-256: `673d3291c4b211f280364748e10a10462c0d45e2797f8301a799a299588ff7c9`
- Motor: `RULES_ONLY`, `prf04-rules-v4`
- Contrato NLP: `schema_version=1.0`
- Proyección del configurador: `PRF04_2`
- Incluye las correcciones semánticas verificadas con las capturas 208 y 209.
- Los artefactos anteriores permanecen conservados para trazabilidad.


## Paquete PRF-04 — 0.1.4 (histórico intermedio)

- Wheel: `homex_nlp-0.1.4-py3-none-any.whl`
- SHA-256: `e6210fc5e2bee1e2b146f36e93c56fa4ee6cca2623063a25037e3c3000a4492e`
- Reglas: `prf04-rules-v5`
- Sustituido por `0.1.5` tras corregir referencias reiteradas al mismo producto.
- Se conserva sin sobrescribir para trazabilidad.

## Paquete operativo PRF-04 — 0.1.5

- Wheel: `homex_nlp-0.1.5-py3-none-any.whl`
- SHA-256: `ccf0b0d87af865faa51ee23d6857565e26599d3b28a52c3a55193e8c5742965f`
- Motor: `RULES_ONLY`, reglas `prf04-rules-v6`
- Contrato: `schema_version=1.0`; proyección `PRF04_2`.
- Incluye extracción comercial y corrección de mención repetida en precios totales.
- La versión operativa la determinan `pyproject.toml`, `uv.lock` y el adaptador.
- El gate F08.4 es histórico y no valida este wheel operativo.

## Paquete operativo PRF-04 — 0.1.13 / reglas v14

- Fuente: https://github.com/gabriel-arinez/homex-nlp/pull/30
- Commit exacto: `0f3ae5b3c406ad037bcb5b0e26de3f5aa2f0a7fe`.
- Wheel: `homex_nlp-0.1.13-py3-none-any.whl` (Python >=3.11,<3.12).
- SHA-256: `42dcf7a32d4ecf21417587de04e0540294c73c41f988c734057150b8722ae9b3`.
- Contrato 1.0, RULES_ONLY, `prf04-rules-v14`, proyección PRF04_2.
- Dos builds independientes con hatchling 1.32.0 produjeron bytes idénticos.
- La procedencia se verificó contra el HEAD de PR #30 y el checkout limpio;
  no se afirma firma criptográfica del autor.

Reproducción (desde un clon de homex-nlp con ese commit disponible):

```bash
git worktree add --detach /tmp/homex-nlp-v14-build 0f3ae5b3c406ad037bcb5b0e26de3f5aa2f0a7fe
cd /tmp/homex-nlp-v14-build
uv build --wheel --out-dir /tmp/nlp-v14-wheel-a
uv build --wheel --out-dir /tmp/nlp-v14-wheel-b
cmp /tmp/nlp-v14-wheel-{a,b}/homex_nlp-0.1.13-py3-none-any.whl
sha256sum /tmp/nlp-v14-wheel-{a,b}/homex_nlp-0.1.13-py3-none-any.whl
```

Desde backend: `sha256sum --check vendor/homex_nlp-0.1.13.sha256`.
El lock fija también el hash. Los wheels históricos se conservan intactos.

## Corrección de voz real — 0.1.14 / reglas v14

Sucede a 0.1.13 sin reemplazar el artefacto histórico. Base NLP #30;
corrección NLP #32 (`4dc3f2532e8a7e406fe63986bab01669682287fe`).
Mantiene contrato 1.0 y proyección PRF04_2.

- Wheel: `homex_nlp-0.1.14-py3-none-any.whl`.
- SHA256: `cdcdbb5c64fa7a0df0ac04495871a365f7a7c2c114b138e7c8ca62a694ecc8f3`.
- Verificación: `sha256sum --check vendor/homex_nlp-0.1.14.sha256`.
- Corrige la herencia de unidad local del alto y la atribución del espesor
  de «una etapa» a cajones. El espesor queda pendiente de asociación humana.
- El aviso NLP de espesor se proyecta una sola vez con resolución
  `ESPESOR_SIN_COMPONENTE`; no queda un aviso genérico imposible de cerrar.

## Consolidación intermedia conservada — 0.1.17

Wheel homex_nlp-0.1.17 y SHA256 fijados, contrato1.0, prf04-rules-final.
Verificar con `sha256sum --check vendor/homex_nlp-0.1.17.sha256`.
No reemplaza bytes históricos; la incorporación futura se documenta en
`docs/implementacion/PRF_04_NLP_FINAL.md`. No autoriza despliegue.

## Motor determinístico definitivo — 0.1.18

Contrato 1.0, RULES_ONLY, prf04-rules-final. Wheel seleccionado por pyproject.toml y uv.lock.
SHA256: `8d594f90e8c7560a2c38039fc6cf8e50e80cfe73be357033937313c05863193c`.
Verificar con `sha256sum --check vendor/homex_nlp-0.1.18.sha256`.
Los wheels anteriores permanecen intactos. No autoriza despliegue.
