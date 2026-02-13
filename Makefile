.PHONY: build test run-paper clean bootstrap review fix harden format autopilot-alert ship-alert

build:
	docker build -t btc-laptop-agents:latest .

test:
	python -m pytest tests/ -v --tb=short -p no:cacheprovider --basetemp=./pytest_temp

run-paper:
	python -m laptop_agents run --mode live-session --async --duration 10 --symbol BTCUSDT

run-docker:
	docker run --rm -it --env-file .env btc-laptop-agents:latest

clean:
	python -c "import shutil, os; [shutil.rmtree(d) for d in ['__pycache__', '.pytest_cache', 'pytest_temp'] if os.path.exists(d)]"
	python -c "import glob, os; [os.remove(f) for f in glob.glob('runs/latest/*.jsonl') + glob.glob('logs/*.log')]"

bootstrap:
	python -m pip install -e .[test]

review:
	powershell -ExecutionPolicy Bypass -File scripts/codex_review.ps1

fix:
	powershell -ExecutionPolicy Bypass -File scripts/codex_fix_loop.ps1

harden:
	powershell -ExecutionPolicy Bypass -File scripts/codex_review.ps1
	python -m mypy src/laptop_agents --ignore-missing-imports --no-error-summary
	python -m pytest tests/ -q --tb=short -p no:cacheprovider --basetemp=./pytest_temp

format:
	python -m ruff format src tests
	python -m ruff check src tests --fix


autopilot-alert:
	python scripts/parallel_alert_build.py --run-codex --merge


ship-alert:
	bash scripts/ship_autopilot.sh $$(git rev-parse --abbrev-ref HEAD)
