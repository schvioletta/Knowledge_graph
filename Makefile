# Knowledge Graph — команды для локальной разработки

.PHONY: help install install-backend install-frontend sample-data backend frontend dev

PORT ?= 8000
GRAPH_DATA_PATH ?=

ifneq (,$(wildcard .venv/bin/python))
PYTHON := .venv/bin/python
else
PYTHON ?= python3
endif

NPM ?= npm

help:
	@echo "Команды:"
	@echo "  make install          — установить зависимости backend и frontend"
	@echo "  make sample-data      — сгенерировать data/sample_graph.json (один раз)"
	@echo "  make backend          — поднять API на http://localhost:$(PORT)"
	@echo "  make frontend         — поднять UI на http://localhost:5173"
	@echo "  make dev              — backend и frontend одновременно"
	@echo ""
	@echo "Переменные:"
	@echo "  PORT=8000             — порт backend"
	@echo "  GRAPH_DATA_PATH=...   — путь к JSON-графу (например data/real_graph.json)"

install: install-backend install-frontend

install-backend:
	$(PYTHON) -m pip install -r requirements.txt

install-frontend:
	cd frontend && $(NPM) install

sample-data:
	$(PYTHON) -m backend.sample_data

backend:
	GRAPH_DATA_PATH=$(GRAPH_DATA_PATH) $(PYTHON) -m uvicorn backend.main:app --reload --port $(PORT)

frontend:
	cd frontend && $(NPM) run dev

dev:
	@echo "Backend: http://localhost:$(PORT)  |  Frontend: http://localhost:5173"
	@trap 'kill 0' INT TERM; \
	GRAPH_DATA_PATH=$(GRAPH_DATA_PATH) $(PYTHON) -m uvicorn backend.main:app --reload --port $(PORT) & \
	cd frontend && $(NPM) run dev; \
	wait
