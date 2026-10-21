.PHONY: install requirements lint test check

install:
	uv sync
	uv run pre-commit install

requirements:
	uv run python -m scripts.requirements.check --write

lint:
	uv run pre-commit run --all-files

test:
	uv run pytest

check: requirements lint test
