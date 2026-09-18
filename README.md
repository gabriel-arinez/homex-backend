# HOMEX Backend

Backend comercial Django/DRF de HOMEX. F07.0 establece proyecto reproducible; aún no implementa el dominio comercial.

```bash
uv sync --extra dev
cp .env.example .env
uv run python manage.py check
uv run pytest
```
