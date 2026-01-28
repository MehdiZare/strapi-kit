.PHONY: help install install-dev test test-verbose test-watch coverage lint format type-check quality clean clean-build clean-pyc clean-test docs docs-serve docs-build release-test release-prod bump-patch bump-minor bump-major

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)py-strapi Development Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

# Installation
install: ## Install package for production use
	@echo "$(BLUE)Installing py-strapi...$(NC)"
	uv pip install -e .

install-dev: ## Install package with development dependencies
	@echo "$(BLUE)Installing py-strapi with dev dependencies...$(NC)"
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

# Pre-commit - Full check before committing
pre-commit: format lint-fix type-check test ## Run full pre-commit checks
	@echo "$(GREEN)✓ Pre-commit checks complete$(NC)"

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
bump-patch: ## Bump patch version (0.1.0 -> 0.1.1)
	@echo "$(BLUE)Bumping patch version...$(NC)"
	bump2version patch
	@echo "$(GREEN)✓ Version bumped$(NC)"

bump-minor: ## Bump minor version (0.1.0 -> 0.2.0)
	@echo "$(BLUE)Bumping minor version...$(NC)"
	bump2version minor
	@echo "$(GREEN)✓ Version bumped$(NC)"

bump-major: ## Bump major version (0.1.0 -> 1.0.0)
	@echo "$(BLUE)Bumping major version...$(NC)"
	bump2version major
	@echo "$(GREEN)✓ Version bumped$(NC)"

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
	@echo "$(BLUE)py-strapi Project Information$(NC)"
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

# Strapi test instance (requires Docker)
strapi-up: ## Start a local Strapi instance for testing (requires Docker)
	@echo "$(BLUE)Starting Strapi test instance...$(NC)"
	@echo "$(YELLOW)Note: This requires Docker to be installed$(NC)"
	docker run -d \
		--name strapi-test \
		-p 1337:1337 \
		-e DATABASE_CLIENT=sqlite \
		-e DATABASE_FILENAME=.tmp/data.db \
		strapi/strapi:latest
	@echo "$(GREEN)✓ Strapi running at http://localhost:1337$(NC)"

strapi-down: ## Stop the local Strapi test instance
	@echo "$(BLUE)Stopping Strapi test instance...$(NC)"
	docker stop strapi-test && docker rm strapi-test
	@echo "$(GREEN)✓ Strapi stopped$(NC)"

# Quick shortcuts
t: test ## Alias for 'test'
tc: type-check ## Alias for 'type-check'
f: format ## Alias for 'format'
l: lint ## Alias for 'lint'
c: coverage ## Alias for 'coverage'
