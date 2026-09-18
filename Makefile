.PHONY: install lint format check test migrate schema

install:
	uv sync --locked --extra dev

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

check:
	uv run python manage.py check
	uv run python manage.py makemigrations --check --dry-run

test:
	uv run pytest -ra

migrate:
	uv run python manage.py migrate --noinput

schema:
	uv run python manage.py spectacular --file docs/openapi.yaml --validate
