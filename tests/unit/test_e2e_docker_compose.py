"""E2E Docker Compose CLI probe (#152 flake: missing docker-compose v1)."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

import pytest

from tests.e2e.conftest import _docker_compose_cmd


def _completed(
    returncode: int, stderr: str = "", stdout: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["docker", "compose", "version"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _probe(
    *,
    run: Callable[..., Any],
    which: Callable[[str], str | None],
    sleep: Callable[[float], None] | None = None,
    retries: int = 1,
    retry_wait: float = 0,
) -> list[str]:
    return _docker_compose_cmd(
        run=run,
        which=which,
        sleep=sleep if sleep is not None else (lambda _seconds: None),
        retries=retries,
        retry_wait=retry_wait,
    )


def test_prefers_compose_plugin_when_probe_succeeds() -> None:
    cmd = _probe(
        run=lambda *_a, **_k: _completed(0, stdout="Docker Compose version v2.29.0"),
        which=lambda name: "/usr/bin/docker" if name == "docker" else None,
    )
    assert cmd == ["docker", "compose"]


def test_does_not_fall_back_to_missing_v1_binary() -> None:
    """#152: a failed plugin probe must not invent `docker-compose`."""
    with pytest.raises(RuntimeError, match="compose plugin not ready"):
        _probe(
            run=lambda *_a, **_k: _completed(1, stderr="compose plugin not ready"),
            which=lambda name: "/usr/bin/docker" if name == "docker" else None,
        )


def test_retries_compose_plugin_probe_then_succeeds() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def run(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        calls["n"] += 1
        if calls["n"] < 3:
            return _completed(1, stderr="not ready")
        return _completed(0, stdout="ok")

    cmd = _probe(
        run=run,
        which=lambda name: "/usr/bin/docker" if name == "docker" else None,
        sleep=sleeps.append,
        retries=5,
        retry_wait=0.5,
    )
    assert cmd == ["docker", "compose"]
    assert calls["n"] == 3
    assert sleeps == [0.5, 0.5]


def test_retries_compose_plugin_after_timeout() -> None:
    calls = {"n": 0}

    def run(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(cmd=["docker", "compose", "version"], timeout=5)
        return _completed(0, stdout="ok")

    cmd = _probe(
        run=run,
        which=lambda name: "/usr/bin/docker" if name == "docker" else None,
        retries=3,
        retry_wait=0,
    )
    assert cmd == ["docker", "compose"]
    assert calls["n"] == 2


def test_falls_back_to_v1_only_when_binary_exists() -> None:
    def run(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "No such file or directory", "docker")

    def which(name: str) -> str | None:
        return "/usr/local/bin/docker-compose" if name == "docker-compose" else None

    assert _probe(run=run, which=which, retries=3) == ["docker-compose"]


def test_does_not_retry_when_docker_is_missing() -> None:
    calls = {"n": 0}

    def run(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        calls["n"] += 1
        raise FileNotFoundError(2, "No such file or directory", "docker")

    with pytest.raises(RuntimeError, match="docker compose"):
        _probe(run=run, which=lambda _name: None, retries=5, retry_wait=0.5)
    assert calls["n"] == 0
