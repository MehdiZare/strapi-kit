# AGENTS.md

Guidance for coding agents working in this repository.

## Repo at a glance
- Package: `py-strapi` (Python client for Strapi REST, sync + async)
- Primary goal: Strapi data migration/backup (bi-directional)
- Source: `src/py_strapi`
- Tests: `tests/unit` (mocked HTTP)

## Essential commands
```bash
# Tests
pytest -v
pytest tests/unit/test_client.py -v

# Type checking (strict)
mypy src/py_strapi/

# Linting + formatting
ruff check src/ tests/
ruff format src/ tests/
```

## Documentation and API claims
- Keep README, `pyproject.toml` metadata, and public docstrings aligned with what is
  implemented. If a feature is planned, label it as planned (no marketing language).
- Update `IMPLEMENTATION_STATUS.md` when functionality changes materially.

## Architecture notes
- **Dual client pattern**: put shared logic in `client/base.py`; keep HTTP calls in
  `client/sync_client.py` and `client/async_client.py`.
- **API version detection**: auto-detects v4 vs v5 on first response and caches it.
  v4 has `data.attributes`, v5 has `data.documentId`. Config override via
  `StrapiConfig(api_version="v4"|"v5")`.
- **API prefix**: endpoints are auto-prefixed with `/api/`. Do not include `/api/`
  in endpoint strings.
- **Error mapping**: HTTP status codes map to semantic exceptions in
  `exceptions/errors.py` (401 auth, 403 authz, 404 not found, 400 validation,
  409 conflict, 429 rate limit, 5xx server).
- **Configuration**: `StrapiConfig` is Pydantic settings; fields can be set via
  `STRAPI_*` environment variables.

## Testing patterns
- Use `respx` to mock HTTP requests.
- Add tests for both sync and async behavior when applicable.
- Cover error mapping, connection/timeout handling, and version detection edge cases.
- Coverage target is 85%+ (raise the bar only with rationale).

## Code quality conventions
- Strict typing (`mypy`) and ruff linting.
- Type hints required for all functions.
- Public classes/functions require Google-style docstrings.
- Always chain exceptions with `raise ... from e`.
- Prefer context managers for clients (`with SyncClient(...)` / `async with ...`).
- Note: `ConnectionError` clashes with builtin; import as `StrapiConnectionError`.

## Production readiness bar
- No unused public config fields (if present, either implement or mark as reserved).
- No unimplemented features advertised as available.
- Tests, mypy, and ruff must be clean before release.

## Roadmap reference
- See `IMPLEMENTATION_STATUS.md` for planned phases (models, import/export).
