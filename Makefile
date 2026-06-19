.PHONY: test run install clean

install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

test:
	.venv/bin/python -m pytest tests/ -v

run:
	.venv/bin/python scraper.py

clean:
	rm -rf __pycache__ .pytest_cache .venv
