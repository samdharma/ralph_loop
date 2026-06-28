# Ralph v3.1 — Makefile
#
# Per docs/IMPROVEMENT_ROADMAP_SPEC.md §5.4.
#
# Targets:
#   install              Symlink bin/ralph into /usr/local/bin or ~/.local/bin
#   test                 Run unit + integration tests
#   test-unit            Run unit tests only
#   test-integration     Run integration tests only
#   lint                 black + isort + flake8 + mypy
#   format               black + isort (apply)
#   validate             ralph validate --tier=targeted against self
#   version-show         Print current version
#   version-bump PART=X  Bump pyproject.toml + core/__init__.py + bin/ralph + tag
#
# Per plan §2.1 order 1: the `release` target is DEFERRED to Phase C (task C-011).
# Per plan §2.1: scripts/release.sh is also deferred to Phase C.

PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
PIP ?= $(PYTHON) -m pip
RALPH_HOME := $(shell pwd)
BIN := $(RALPH_HOME)/bin/ralph

# Resolve the user's preferred install location.
ifeq ($(wildcard $(HOME)/.local/bin),)
INSTALL_PREFIX := /usr/local
else
INSTALL_PREFIX := $(HOME)/.local
endif

.PHONY: help install test test-unit test-integration lint format validate version-show version-bump release clean

help:  ## Show this help.
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ─────────────────────────────────────────────────────────
# Install
# ─────────────────────────────────────────────────────────

install:  ## Symlink bin/ralph into $(INSTALL_PREFIX)/bin.
	@mkdir -p $(INSTALL_PREFIX)/bin
	@ln -sf $(BIN) $(INSTALL_PREFIX)/bin/ralph
	@echo "Installed: $(INSTALL_PREFIX)/bin/ralph -> $(BIN)"
	@echo "Run '$(BIN) version' to verify."

# ─────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────

test: test-unit test-integration  ## Run unit + integration tests.

test-unit:  ## Run unit tests.
	$(PYTHON) -m pytest tests/unit/ -q

test-integration:  ## Run integration tests.
	$(PYTHON) -m pytest tests/integration/ -q

test-e2e:  ## Run E2E tests (requires RALPH_E2E=1 and a real GitHub repo).
	RALPH_E2E=1 $(PYTHON) -m pytest tests/e2e/ -v

# ─────────────────────────────────────────────────────────
# Lint
# ─────────────────────────────────────────────────────────

lint:  ## black + isort + flake8 + mypy (check only).
	$(PYTHON) -m black --target-version py310 --check core tests bin
	$(PYTHON) -m isort --check-only --profile black core tests bin
	$(PYTHON) -m flake8 core tests bin
	$(PYTHON) -m mypy --explicit-package-bases core/validate.py core/pipeline/

format:  ## black + isort (apply).
	$(PYTHON) -m black --target-version py310 core tests bin
	$(PYTHON) -m isort --profile black core tests bin

# ─────────────────────────────────────────────────────────
# Validate
# ─────────────────────────────────────────────────────────

validate:  ## ralph validate --tier=targeted against self (Ralph validates its own test suite + pytest).
	$(PYTHON) -m pytest tests/unit/ tests/integration/ -q
	$(PYTHON) core/validate.py --tier=targeted

# ─────────────────────────────────────────────────────────
# Versioning
# ─────────────────────────────────────────────────────────

version-show:  ## Print current version.
	@$(PYTHON) -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); print(d['project']['version'])"

# PART must be one of: major, minor, patch.
version-bump:  ## Bump version. Usage: make version-bump PART=minor
	@if [[ -z "$(PART)" ]]; then echo "Usage: make version-bump PART=<major|minor|patch>"; exit 1; fi
	@$(PYTHON) scripts/version_bump.py $(PART)

release:  ## Tag + push + gh release create. Usage: make release PART=patch
	@if [[ -z "$(PART)" ]]; then echo "Usage: make release PART=<major|minor|patch>"; exit 1; fi
	@$(PYTHON) scripts/version_bump.py $(PART)
	@NEW_VERSION=$$(grep '^version = ' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/'); \
	echo "==> Tagging ralph-v$$NEW_VERSION..."; \
	./scripts/release.sh "$$NEW_VERSION"

# ─────────────────────────────────────────────────────────
# Misc
# ─────────────────────────────────────────────────────────

clean:  ## Remove caches and pyc files.
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true