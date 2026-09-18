# Alles läuft als Modul vom Repo-Root (siehe CLAUDE.md §6). Das Frontend ist eine
# einzelne HTML-Datei, die FastAPI unter / ausliefert — kein separater Dev-Server.

.PHONY: dev test lint format format-check smoke eval-llm demo facts

dev:            ## Backend + Frontend: http://localhost:8000
	uv run uvicorn uro.api:app --reload --port 8000

test:           ## Unit-Tests
	uv run pytest -q

lint:           ## Ruff check (E, F, I, UP, B) über uro, tests, eval — Pflicht vor jedem Commit
	uv run ruff check uro tests eval

format:         ## Ruff format nur auf die eigenen Dateien anwenden: make format FILES="uro/analytics/saa.py"
	uv run ruff format $(or $(FILES),uro tests eval)

format-check:   ## Zeigt, welche Dateien Ruff umformatieren würde (kein Gate — fremde Dateien nicht anfassen)
	uv run ruff format --check uro tests eval

smoke:          ## Engine über alle Klienten, ohne LLM (Exit ≠ 0 bei Fehler)
	uv run python -m eval.run_all

eval-llm:       ## Engine + echtes Briefing je Klient (braucht ANTHROPIC_API_KEY; --limit kommt in C4)
	uv run python -m eval.run_all --briefings

demo:           ## Durchstich für einen Klienten inkl. LLM (REF=CASE-003)
	uv run python -m uro.demo $(or $(REF),CASE-003)

facts:          ## Nur die Engine für einen Klienten (REF=CASE-003)
	uv run python -m uro.demo $(or $(REF),CASE-003) --facts
