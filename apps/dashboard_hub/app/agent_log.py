from __future__ import annotations

from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from app.config import AGENT_LOG_RETENTION

_current_replay_id: ContextVar[str] = ContextVar("current_replay_id", default="")
_current_request_id: ContextVar[str] = ContextVar("current_request_id", default="")
_log_buffer: deque[dict[str, Any]] = deque(maxlen=AGENT_LOG_RETENTION)
_log_lock = Lock()


def set_request_context(replay_id: str | None) -> tuple[Any, Any]:
    normalized_replay_id = (replay_id or "").strip()
    request_id = uuid4().hex
    replay_token = _current_replay_id.set(normalized_replay_id)
    request_token = _current_request_id.set(request_id)
    return replay_token, request_token


def clear_request_context(tokens: tuple[Any, Any]) -> None:
    replay_token, request_token = tokens
    _current_replay_id.reset(replay_token)
    _current_request_id.reset(request_token)


def get_current_replay_id() -> str:
    return _current_replay_id.get()


def get_current_request_id() -> str:
    return _current_request_id.get()


def record_event(event: str, **fields: Any) -> None:
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "replay_id": get_current_replay_id() or None,
        "request_id": get_current_request_id() or None,
    }
    for key, value in fields.items():
        if value is None:
            continue
        entry[key] = value
    with _log_lock:
        _log_buffer.append(entry)


def read_logs(*, replay_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    normalized_replay_id = (replay_id or "").strip()
    with _log_lock:
        items = list(_log_buffer)
    if normalized_replay_id:
        items = [item for item in items if item.get("replay_id") == normalized_replay_id]
    if limit <= 0:
        return []
    return items[-limit:]
