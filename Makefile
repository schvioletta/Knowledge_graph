# Knowledge Graph — команды для локальной разработки

.PHONY: help install install-backend install-frontend sample-data backend frontend dev

PORT ?= 8000
GRAPH_DATA_PATH ?=

ifneq (,$(wildcard .venv/bin/python))
PYTHON := .venv/bin/python
else
PYTHON ?= python3
endif

# Node.js / npm: системный PATH или nvm (npm — symlink на скрипт с #!/usr/bin/env node,
# поэтому node должен быть в PATH через export, а не только prefix перед вызовом npm).
NODE := $(shell command -v node 2>/dev/null)
ifeq ($(NODE),)
NODE := $(shell ls $(HOME)/.nvm/versions/node/*/bin/node 2>/dev/null | tail -1)
endif
NODE_BIN_DIR := $(dir $(NODE))
NPM := $(shell command -v npm 2>/dev/null)
ifeq ($(NPM),)
NPM := $(NODE_BIN_DIR)npm
endif
ifeq ($(NPM),npm)
# node и npm не найдены — команды frontend упадут с понятной ошибкой
endif

# Обёртка: гарантирует node в PATH для npm/vite (shebang /usr/bin/env node).
define RUN_NPM
	cd $(1) && export PATH="$(NODE_BIN_DIR):$$PATH" && $(NPM) $(2)
endef

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
	$(call RUN_NPM,frontend,install)

sample-data:
	$(PYTHON) -m backend.sample_data

backend:
	GRAPH_DATA_PATH=$(GRAPH_DATA_PATH) $(PYTHON) -m uvicorn backend.main:app --reload --host 0.0.0.0 --port $(PORT)

frontend:
	$(call RUN_NPM,frontend,run dev)

dev:
	@echo "Backend: http://0.0.0.0:$(PORT)  |  Frontend: http://0.0.0.0:5173"
	@trap 'kill 0' INT TERM; \
	GRAPH_DATA_PATH=$(GRAPH_DATA_PATH) $(PYTHON) -m uvicorn backend.main:app --reload --host 0.0.0.0 --port $(PORT) & \
	$(call RUN_NPM,frontend,run dev); \
	wait
