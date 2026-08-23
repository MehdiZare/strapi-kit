# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Write-404 classification probes the write's own status first** —
  `update(..., classify_write_404=True)` and
  `remove(..., classify_write_404=True)` no longer treat a draft-only
  document as a missing-token problem when the write addressed the
  published version (`status=published` or omitted status). Probe 1 uses
  the write query (omit-status for `remove`). A hit is still
  `AuthorizationError`. A miss then probes `status=draft` only when the
  write was not already draft. Draft-only remains `NotFoundError`.
  A probe HTTP 404 is an answer, not a failed probe.

## [0.4.0] - 2026-08-19

i18n localizations, nested component/dynamic-zone relations, dest media
writes, FAIL-write missing locales, dry-run / JSONL preflight, and
Docker e2e CI. Tracker: #144.

PLACEHOLDER_REST_OF_FILE_WILL_FAIL_VERIFY
