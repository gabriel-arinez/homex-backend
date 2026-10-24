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
