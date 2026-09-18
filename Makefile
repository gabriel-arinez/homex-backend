.PHONY: check test lint schema
check: lint test
lint:
	uv run ruff check .
	uv run ruff format --check .
test:
	uv run pytest
schema:
	DJANGO_SETTINGS_MODULE=config.settings.test uv run python manage.py spectacular --file docs/openapi.yaml --validate
