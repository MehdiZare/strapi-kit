# Repository Guidelines

## Project Structure & Module Organization
- `src/strapi_kit/`: library source (clients, models, query builder, migrations, etc.).
- `tests/`: automated tests organized by scope: `unit/`, `integration/`, `e2e/`.
- `docs/`: MkDocs documentation source; `site/` is generated output.
- `examples/`: runnable usage samples and migration scripts.

## Build, Test, and Development Commands
```bash
# Install (uv preferred)
uv pip install -e ".[dev]"    # or: make install-dev

# Quality and tests
make test                     # pytest
make coverage                 # coverage report (htmlcov/)
make lint                     # ruff check
make format                   # ruff format
make type-check               # mypy strict
make pre-commit               # format + lint-fix + type-check + test

# Docs
make docs-serve               # local docs at http://127.0.0.1:8000

# E2E (requires Strapi via Docker)
make e2e-setup                # start Strapi
make e2e                      # run e2e tests
make e2e-teardown             # stop Strapi
```

## Coding Style & Naming Conventions
- Python 3.12+, PEP 8, line length 100 (enforced by Ruff).
- Use `ruff format` for formatting and `ruff check` for linting.
- `mypy` runs in strict mode on `src/strapi_kit/`; type hints are expected for all functions.
- Prefer f-strings and Google-style docstrings.
- Use project exception types (e.g., from `strapi_kit.exceptions`) and chain errors with `raise ... from e`.

## Testing Guidelines
- Frameworks: `pytest`, `pytest-asyncio` (auto mode), `respx` for HTTP mocking.
- Naming: `test_*.py`, `Test*` classes, `test_*` functions (per pytest config).
- Organize by scope: unit tests are fast/isolated; integration tests require a real Strapi instance; e2e tests are Docker-backed.
- Coverage target: 85%+ overall.

## Commit & Pull Request Guidelines
- Recent history uses descriptive sentence-style messages (e.g., “Add…”, “Refactor…”), but the contributing guide requests **Conventional Commits**.
- Use conventional commit format in commits and PR titles, e.g. `feat(client): add retry logic`.
- PRs should describe what/why, link issues, note breaking changes, and include screenshots for UI changes.
- Expect automated review by CodeRabbit; ensure `pytest`, `mypy`, and `ruff` pass.

## Security & Configuration
- Run security checks with `make security` (Bandit). Use `make security-baseline` to refresh `.secrets.baseline` when needed.

## Agent-Specific Instructions
- If you are an AI assistant, consult `CLAUDE.md` and `LLM.md` for workflow conventions and architecture notes.
