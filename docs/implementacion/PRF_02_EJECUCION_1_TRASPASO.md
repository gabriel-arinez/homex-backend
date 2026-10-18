# PRF-02 — Traspaso de Ejecución 1

1. Rama backend: `feat/prf02-backend-contrato`.
2. Base documental/backend: `d7ab4e9`; frontend compartido: `44af8ad`.
3. El listado de productos publica y ejecuta todos los filtros PRF-02 en SQL.
4. Los filtros específicos exigen categoría y rechazan conceptos/combinaciones inválidos con 400.
5. Las opciones inactivadas siguen disponibles como filtro histórico.
6. Paginación y búsqueda existentes se conservaron.
7. Demanda y disponibilidad usan una agregación SQL; no existe N+1 por SKU.
8. La resolución pendiente conserva la línea y sus valores comerciales negociados.
9. PostgreSQL conserva la autoridad de compatibilidad, unidades, unicidad y aprobación.
10. El PDF advierte que la variante pendiente no tiene SKU ni stock reservado.
11. No se añadieron tablas ni migraciones.
12. OpenAPI es el contrato para regenerar tipos TypeScript en la siguiente ejecución.
13. Pruebas backend focalizadas en PostgreSQL 17: 33 aprobadas.
14. Pendiente: implementar PRF-02 frontend y su integración, E2E y accesibilidad.
15. PRF-02 no está declarada completa.
