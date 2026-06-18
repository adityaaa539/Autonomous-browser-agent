.PHONY: install db-up db-down migrate test run lint

install:
	pip install poetry && poetry install && poetry run playwright install

db-up:
	docker-compose up -d

db-down:
	docker-compose down

migrate:
	poetry run alembic upgrade head

test:
	poetry run pytest

run:
	poetry run uvicorn api.main:app --reload

lint:
	poetry run ruff check . || true
