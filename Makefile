.PHONY: build test run-paper clean bootstrap review fix harden

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
