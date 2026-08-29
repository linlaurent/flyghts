"""Track Streamlit widget interactions for local debugging.

Logs JSON lines to stderr and logs/user_actions_YYYY-MM-DD.log. Disable with
FLYGHITS_ACTION_LOG=0.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from .config import PROJECT_ROOT

_LOGGER_NAME = "flyghts.action"
_ENV_FLAG = "FLYGHITS_ACTION_LOG"
_SESSION_ID_KEY = "_action_log_session_id"
_PREV_KEY = "_action_log_prev"
_STARTED_KEY = "_action_log_started"
_HANDLERS_READY = False
_FILE_HANDLER: logging.FileHandler | None = None
_FILE_HANDLER_DATE: date | None = None

LOG_DIR = PROJECT_ROOT / "logs"


def log_file_path(day: date | None = None) -> Path:
    """Return the dated action log path for the given day (default: today)."""
    d = day or date.today()
    return LOG_DIR / f"user_actions_{d.isoformat()}.log"


def action_log_enabled() -> bool:
    """Return True unless FLYGHITS_ACTION_LOG is set to a falsey value."""
    raw = os.environ.get(_ENV_FLAG, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def serialize_value(value: Any) -> Any:
    """Convert widget values to JSON-serializable forms."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return [serialize_value(v) for v in sorted(value, key=str)]
    if isinstance(value, tuple):
        return [serialize_value(v) for v in value]
    if isinstance(value, list):
        return [serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): serialize_value(v) for k, v in value.items()}
    if isinstance(value, Path):
        return str(value)
    return value


def values_equal(a: Any, b: Any) -> bool:
    """Compare two widget values after serialization."""
    return serialize_value(a) == serialize_value(b)


def _auto_key(widget: str, label: str) -> str:
    return f"_action_log::{widget}::{label}"


def _attach_dated_file_handler(logger: logging.Logger) -> None:
    """Ensure the file handler targets today's dated log path."""
    global _FILE_HANDLER, _FILE_HANDLER_DATE
    today = date.today()
    if _FILE_HANDLER is not None and _FILE_HANDLER_DATE == today:
        return

    if _FILE_HANDLER is not None:
        logger.removeHandler(_FILE_HANDLER)
        _FILE_HANDLER.close()
        _FILE_HANDLER = None

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(message)s")
    file_handler = logging.FileHandler(log_file_path(today), encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    _FILE_HANDLER = file_handler
    _FILE_HANDLER_DATE = today


def _ensure_handlers() -> logging.Logger:
    global _HANDLERS_READY
    logger = logging.getLogger(_LOGGER_NAME)
    if not _HANDLERS_READY:
        logger.setLevel(logging.INFO)
        logger.propagate = False
        formatter = logging.Formatter("%(message)s")

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        _HANDLERS_READY = True

    _attach_dated_file_handler(logger)
    return logger


def _session_id() -> str:
    if _SESSION_ID_KEY not in st.session_state:
        st.session_state[_SESSION_ID_KEY] = uuid.uuid4().hex[:8]
    return st.session_state[_SESSION_ID_KEY]


def _prev_store() -> dict[str, Any]:
    if _PREV_KEY not in st.session_state:
        st.session_state[_PREV_KEY] = {}
    return st.session_state[_PREV_KEY]


def emit_event(action: str, **payload: Any) -> None:
    """Write one JSON log line (no-op when logging is disabled)."""
    if not action_log_enabled():
        return
    logger = _ensure_handlers()
    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "session": _session_id(),
        "action": action,
        **{k: serialize_value(v) for k, v in payload.items()},
    }
    logger.info(json.dumps(record, default=str))


def track_widget(
    widget: str,
    label: str,
    value: Any,
    *,
    key: str | None = None,
) -> Any:
    """Log a widget value when it differs from the previous run."""
    if not action_log_enabled():
        return value

    track_key = key or _auto_key(widget, label)
    prev = _prev_store()
    if track_key in prev:
        previous = prev[track_key]
        if not values_equal(previous, value):
            emit_event(
                "widget_change",
                widget=widget,
                label=label,
                key=track_key,
                value=value,
                previous=previous,
            )
    prev[track_key] = serialize_value(value)
    return value


def init_action_logger() -> None:
    """Configure handlers and emit session_start once per browser session."""
    if not action_log_enabled():
        return
    _ensure_handlers()
    if not st.session_state.get(_STARTED_KEY):
        st.session_state[_STARTED_KEY] = True
        emit_event("session_start")


def _track_call(widget: str, label: str, value: Any, kwargs: dict[str, Any]) -> Any:
    return track_widget(widget, label, value, key=kwargs.get("key"))


def radio(label: str, *args: Any, **kwargs: Any) -> Any:
    value = st.radio(label, *args, **kwargs)
    return _track_call("radio", label, value, kwargs)


def selectbox(label: str, *args: Any, **kwargs: Any) -> Any:
    value = st.selectbox(label, *args, **kwargs)
    return _track_call("selectbox", label, value, kwargs)


def multiselect(label: str, *args: Any, **kwargs: Any) -> Any:
    value = st.multiselect(label, *args, **kwargs)
    return _track_call("multiselect", label, value, kwargs)


def slider(label: str, *args: Any, **kwargs: Any) -> Any:
    value = st.slider(label, *args, **kwargs)
    return _track_call("slider", label, value, kwargs)


def date_input(label: str, *args: Any, **kwargs: Any) -> Any:
    value = st.date_input(label, *args, **kwargs)
    return _track_call("date_input", label, value, kwargs)


def text_input(label: str, *args: Any, **kwargs: Any) -> Any:
    value = st.text_input(label, *args, **kwargs)
    return _track_call("text_input", label, value, kwargs)


def number_input(label: str, *args: Any, **kwargs: Any) -> Any:
    value = st.number_input(label, *args, **kwargs)
    return _track_call("number_input", label, value, kwargs)


def checkbox(label: str, *args: Any, **kwargs: Any) -> Any:
    value = st.checkbox(label, *args, **kwargs)
    return _track_call("checkbox", label, value, kwargs)


def button(label: str, *args: Any, **kwargs: Any) -> bool:
    clicked = st.button(label, *args, **kwargs)
    _track_call("button", label, clicked, kwargs)
    return clicked
