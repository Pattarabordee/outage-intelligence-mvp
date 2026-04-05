.PHONY: install run test demo seed

install:
	python -m pip install -r requirements.txt

run:
	uvicorn apps.api.main:app --reload

test:
	pytest -q

demo:
	python -m apps.api.demo_scenario

seed:
	python scripts/seed_demo_data.py
