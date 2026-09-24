.PHONY: setup test lint check run

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .

check:
	.venv/bin/python main.py --check

run:
	.venv/bin/python main.py
