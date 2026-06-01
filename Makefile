.PHONY: install run test coverage demo seed export baseline evaluate

install:
	python -m pip install -r requirements.txt

run:
	uvicorn apps.api.main:app --reload

test:
	pytest -q

coverage:
	pytest --cov=apps --cov-report=term-missing --cov-fail-under=80

demo:
	python -m apps.api.demo_scenario

seed:
	python scripts/seed_demo_data.py

export:
	python scripts/export_closed_dataset.py

baseline:
	python scripts/train_eta_baseline.py

evaluate:
	python scripts/evaluate_product_metrics.py
