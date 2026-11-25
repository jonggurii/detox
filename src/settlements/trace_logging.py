"""Moa settlement request traces: metadata only, never input text, names or amounts.

No authentication headers, raw URLs, JSON bodies, user names, image data, or exception
messages are logged. A single JSONL event is appended per application API request.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import perf_counter
import json
import logging
import os
import re
import subprocess
from functools import lru_cache
import uuid

_LOG = logging.getLogger(__name__)
_ACTIVE: ContextVar[dict | None] = ContextVar("settlement_trace", default=None)
_LOCK = Lock()
_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "logs" / "trace.jsonl"


def _safe_length(value: str | None) -> int | None:
    try:
        number = int(value) if value is not None else None
        return number if number is not None and 0 <= number <= 20_000_000 else None
    except (TypeError, ValueError):
        return None


def _file_path() -> Path:
    return Path(os.getenv("SETTLEMENT_TRACE_PATH", str(_DEFAULT_PATH)))


def _append(record: dict) -> None:
    """Append without disturbing product operation if log storage is unavailable."""
    try:
        path = _file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with _LOCK:
            fd = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                stream.write(line)
    except OSError:
        _LOG.warning("Trace storage unavailable (input not logged)")


@lru_cache(maxsize=1)
def _local_git_commit() -> str:
    """Read local revision once per process; never capture or log Git stderr."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_DEFAULT_PATH.parents[1],
            check=True, capture_output=True, text=True, timeout=2,
        )
        value = completed.stdout.strip()
        return value if re.fullmatch(r"[0-9a-fA-F]{7,40}", value) else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _current_commit() -> str:
    """Prefer the deployment revision; fall back to the local Git checkout."""
    value = (os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or "").strip()
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", value):
        return value
    return _local_git_commit()


def set_trace_model(model: str, prompt_version: str) -> None:
    """Annotate the active API trace only when an actual model call is attempted.

    Never pass a prompt body, exception text, request content, token, or username.
    """
    current = _ACTIVE.get()
    if current is None:
        return  # CLI evals run without an API request trace.
    if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9._/-]{1,128}", model):
        current["model"] = model
    if (isinstance(prompt_version, str) and len(prompt_version) <= 100
            and re.fullmatch(r"[A-Za-z0-9._:/ -]+", prompt_version)):
        current["prompt_version"] = prompt_version


@contextmanager
def trace_stage(stage: str):
    """Capture a fixed stage name, duration and an exception class, not its message."""
    current = _ACTIVE.get()
    started = perf_counter()
    failure = None
    try:
        yield
    except Exception as exc:
        failure = type(exc).__name__
        raise
    finally:
        if current is not None:
            current["stages"].append({
                "name": stage,
                "status": "error" if failure else "ok",
                "latency_ms": round((perf_counter() - started) * 1000, 2),
                "error_type": failure,
            })


async def trace_request(request, call_next):
    """ASGI/FastAPI middleware; only product endpoints are traced.

    Store endpoint route templates rather than session IDs embedded in actual paths.
    """
    path = request.url.path
    if not (path.startswith("/api/") or path == "/parse"):
        return await call_next(request)

    try:
        from .gemini_client import get_model
        model = get_model()
    except Exception:
        model = "unavailable"
    record = {
        "request_id": "q-" + uuid.uuid4().hex[:12],
        "ts": datetime.now(timezone.utc).isoformat(),
        "input": {
            "method": request.method,
            "kind": ("multipart" if "multipart/" in request.headers.get("content-type", "") else "json" if "application/json" in request.headers.get("content-type", "") else "other"),
            "bytes": _safe_length(request.headers.get("content-length")),
        },
        "stages": [],
        "output": {"status_code": 500, "status": "failed"},
        "commit": _current_commit(),
        "model": "not-called",
        "prompt_version": "not-applicable",
        "latency_ms": 0,
        "error": None,
    }
    token = _ACTIVE.set(record)
    started = perf_counter()
    try:
        response = await call_next(request)
        code = response.status_code
        record["output"] = {"status_code": code, "status": "ok" if code < 400 else "failed"}
        if code >= 400:
            record["error"] = "HTTP_" + str(code)
        response.headers["X-Request-ID"] = record["request_id"]
        return response
    except Exception as exc:
        record["error"] = type(exc).__name__
        raise
    finally:
        # Never store raw request.url.path: it can contain a private session ID.
        route = request.scope.get("route")
        template = getattr(route, "path", None)
        record["route"] = template if isinstance(template, str) and template.startswith("/") else "unmatched_route"
        record["latency_ms"] = round((perf_counter() - started) * 1000, 2)
        _ACTIVE.reset(token)
        _append(record)
