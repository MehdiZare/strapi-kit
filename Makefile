.PHONY: help install install-dev test test-verbose test-watch coverage lint format type-check quality security security-baseline install-hooks run-hooks update-hooks clean clean-build clean-pyc clean-test docs docs-serve docs-build release-test release-prod bump-patch bump-minor bump-major

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)strapi-kit Development Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

# Installation
install: ## Install package for production use
	@echo "$(BLUE)Installing strapi-kit...$(NC)"
	uv pip install -e .

install-dev: ## Install package with development dependencies
	@echo "$(BLUE)Installing strapi-kit with dev dependencies...$(NC)"
	uv pip install -e ".[dev]"
	@echo "$(GREEN)✓ Installation complete$(NC)"

# Testing
test: ## Run tests
	@echo "$(BLUE)Running tests...$(NC)"
	pytest

test-verbose: ## Run tests with verbose output
	@echo "$(BLUE)Running tests (verbose)...$(NC)"
	pytest -v

test-watch: ## Run tests in watch mode
	@echo "$(BLUE)Running tests in watch mode...$(NC)"
	pytest-watch

test-specific: ## Run specific test file (use TEST=path/to/test.py)
	@echo "$(BLUE)Running specific test: $(TEST)...$(NC)"
	pytest $(TEST) -v

coverage: ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	pytest --cov=py_strapi --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Coverage report generated in htmlcov/index.html$(NC)"

coverage-xml: ## Generate XML coverage report for CI
	@echo "$(BLUE)Generating XML coverage report...$(NC)"
	pytest --cov=py_strapi --cov-report=xml

# Code Quality
lint: ## Run linting checks
	@echo "$(BLUE)Running linting checks...$(NC)"
	ruff check src/ tests/
	@echo "$(GREEN)✓ Linting complete$(NC)"

lint-fix: ## Run linting and auto-fix issues
	@echo "$(BLUE)Running linting with auto-fix...$(NC)"
	ruff check src/ tests/ --fix
	@echo "$(GREEN)✓ Linting complete$(NC)"

format: ## Format code with ruff
	@echo "$(BLUE)Formatting code...$(NC)"
	ruff format src/ tests/
	@echo "$(GREEN)✓ Code formatted$(NC)"

format-check: ## Check if code is formatted correctly
	@echo "$(BLUE)Checking code formatting...$(NC)"
	ruff format --check src/ tests/

type-check: ## Run type checking with mypy
	@echo "$(BLUE)Running type checks...$(NC)"
	mypy src/py_strapi/
	@echo "$(GREEN)✓ Type checking complete$(NC)"

quality: lint type-check ## Run all quality checks (lint + type-check)
	@echo "$(GREEN)✓ All quality checks passed$(NC)"

security: ## Run security checks (bandit)
	@echo "$(BLUE)Running security checks...$(NC)"
	bandit -c pyproject.toml -r src/
	@echo "$(GREEN)✓ Security checks complete$(NC)"

security-baseline: ## Create baseline for detect-secrets
	@echo "$(BLUE)Creating detect-secrets baseline...$(NC)"
	detect-secrets scan > .secrets.baseline
	@echo "$(GREEN)✓ Baseline created at .secrets.baseline$(NC)"

# Pre-commit hooks
install-hooks: ## Install pre-commit hooks
	@echo "$(BLUE)Installing pre-commit hooks...$(NC)"
	pre-commit install
	@echo "$(GREEN)✓ Pre-commit hooks installed successfully!$(NC)"

run-hooks: ## Run all pre-commit hooks manually
	@echo "$(BLUE)Running pre-commit hooks on all files...$(NC)"
	pre-commit run --all-files

update-hooks: ## Update pre-commit hooks to latest versions
	@echo "$(BLUE)Updating pre-commit hooks...$(NC)"
	pre-commit autoupdate
	@echo "$(GREEN)✓ Pre-commit hooks updated$(NC)"

# Pre-commit - Full check before committing
pre-commit: format lint-fix type-check test ## Run full pre-commit checks
	@echo "$(GREEN)✓ Pre-commit checks complete$(NC)"
	@echo "$(YELLOW)💡 Tip: Install git hooks with 'make install-hooks' to run checks automatically$(NC)"

# Documentation
docs: ## Build documentation
	@echo "$(BLUE)Building documentation...$(NC)"
	mkdocs build
	@echo "$(GREEN)✓ Documentation built in site/$(NC)"

docs-serve: ## Serve documentation locally
	@echo "$(BLUE)Serving documentation at http://127.0.0.1:8000$(NC)"
	mkdocs serve

docs-deploy: ## Deploy documentation to GitHub Pages
	@echo "$(BLUE)Deploying documentation...$(NC)"
	mkdocs gh-deploy --force
	@echo "$(GREEN)✓ Documentation deployed$(NC)"

# Cleaning
clean: clean-build clean-pyc clean-test ## Remove all build, test, coverage and Python artifacts
	@echo "$(GREEN)✓ Cleaned all artifacts$(NC)"

clean-build: ## Remove build artifacts
	@echo "$(YELLOW)Cleaning build artifacts...$(NC)"
	rm -rf build/
	rm -rf dist/
	rm -rf .eggs/
	find . -name '*.egg-info' -exec rm -rf {} +
	find . -name '*.egg' -exec rm -rf {} +

clean-pyc: ## Remove Python file artifacts
	@echo "$(YELLOW)Cleaning Python artifacts...$(NC)"
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -rf {} +

clean-test: ## Remove test and coverage artifacts
	@echo "$(YELLOW)Cleaning test artifacts...$(NC)"
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml

# Building & Distribution
build: clean ## Build source and wheel distributions
	@echo "$(BLUE)Building distribution packages...$(NC)"
	python -m build
	@echo "$(GREEN)✓ Build complete - packages in dist/$(NC)"

# Version Management
# Note: Versioning is git-tag based via hatch-vcs
# To create a new version, create and push a git tag:
#   git tag -a v0.2.0 -m "Release v0.2.0"
#   git push origin v0.2.0

# Release
release-check: quality test coverage ## Run all checks before release
	@echo "$(GREEN)✓ All checks passed - ready for release$(NC)"

release-test: build ## Build and upload to TestPyPI
	@echo "$(BLUE)Uploading to TestPyPI...$(NC)"
	twine upload --repository testpypi dist/*
	@echo "$(GREEN)✓ Uploaded to TestPyPI$(NC)"

release-prod: build ## Build and upload to PyPI
	@echo "$(RED)Uploading to PyPI...$(NC)"
	twine upload dist/*
	@echo "$(GREEN)✓ Uploaded to PyPI$(NC)"

# Development helpers
shell: ## Start Python shell with project loaded
	@python -c "import py_strapi; import IPython; IPython.embed()"

info: ## Show project information
	@echo "$(BLUE)strapi-kit Project Information$(NC)"
	@echo ""
	@echo "  Python version:    $$(python --version)"
	@echo "  Package version:   $$(python -c 'import py_strapi; print(py_strapi.__version__)' 2>/dev/null || echo 'Not installed')"
	@echo "  Project root:      $$(pwd)"
	@echo ""

todo: ## Show TODO items in code
	@echo "$(BLUE)TODO items in code:$(NC)"
	@grep -rn "TODO\|FIXME\|XXX" src/ tests/ --color=always || echo "  $(GREEN)No TODOs found$(NC)"

# Git helpers
git-status: ## Show git status and branch info
	@echo "$(BLUE)Git Status:$(NC)"
	@git status
	@echo ""
	@echo "$(BLUE)Recent commits:$(NC)"
	@git log --oneline -5

# Strapi test instance (TODO - not yet implemented)
# Integration tests with Docker-based Strapi instance are planned for future phases
	@echo "$(GREEN)✓ Strapi stopped$(NC)"

# Quick shortcuts
t: test ## Alias for 'test'
tc: type-check ## Alias for 'type-check'
f: format ## Alias for 'format'
l: lint ## Alias for 'lint'
c: coverage ## Alias for 'coverage'
