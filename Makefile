SHELL := /bin/bash

.PHONY: help check-env check-env-file precommit-install precommit-run precommit-update baseline-generate baseline-audit setup

ENV_FILE ?= .env

help:
	@echo "Available targets:"
	@echo "  make setup                 - Install hooks + sync LINE service deps (one-time bootstrap)"
	@echo "  make check-env             - Validate required LINE env vars from process environment"
	@echo "  make check-env-file        - Validate required LINE env vars from ENV_FILE (.env by default)"
	@echo "  make precommit-install     - Install pre-commit + detect-secrets and enable git hook"
	@echo "  make precommit-run         - Run pre-commit hooks on all files"
	@echo "  make precommit-update      - Update pinned hook versions"
	@echo "  make baseline-generate     - Regenerate .secrets.baseline"
	@echo "  make baseline-audit        - Audit baseline interactively"

check-env:
	uv run scripts/check_env.py

check-env-file:
	uv run scripts/check_env.py --env-file $(ENV_FILE)

precommit-install:
	uv tool install pre-commit --quiet
	uv tool install detect-secrets --quiet
	uv tool run pre-commit install

precommit-run:
	uv tool run pre-commit run --all-files

precommit-update:
	uv tool run pre-commit autoupdate

baseline-generate:
	uv tool run detect-secrets scan --exclude-files '\\.secrets\\.baseline|.*\\.lock$$|uv\\.lock$$|package-lock\\.json$$' > .secrets.baseline

baseline-audit:
	uv tool run detect-secrets audit .secrets.baseline

setup: precommit-install
	@echo ""
	@echo "→ Syncing LINE service dependencies (line/)..."
	cd line && uv sync
	@echo ""
	@echo "Installed packages:"
	cd line && uv pip list
	@echo ""
	@echo "Bootstrap complete."
	@echo "Next → run 'make check-env' to validate LINE credentials before starting the server."
