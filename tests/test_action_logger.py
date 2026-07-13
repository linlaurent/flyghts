"""Unit tests for dashboard action logger helpers."""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

STREAMLIT_DIR = Path(__file__).resolve().parent.parent / "streamlit"
if str(STREAMLIT_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_DIR))

from dashboard.action_logger import (  # noqa: E402
    action_log_enabled,
    log_file_path,
    serialize_value,
    values_equal,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("true", True),
        ("", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        ("FALSE", False),
    ],
)
def test_action_log_enabled(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    if raw == "":
        monkeypatch.delenv("FLYGHITS_ACTION_LOG", raising=False)
    else:
        monkeypatch.setenv("FLYGHITS_ACTION_LOG", raw)
    assert action_log_enabled() is expected


def test_log_file_path_includes_date() -> None:
    path = log_file_path(date(2026, 7, 13))
    assert path.name == "user_actions_2026-07-13.log"
    assert path.parent.name == "logs"


def test_serialize_value_dates_and_collections() -> None:
    assert serialize_value(date(2026, 7, 13)) == "2026-07-13"
    assert serialize_value(datetime(2026, 7, 13, 14, 31, 2)) == "2026-07-13T14:31:02"
    assert serialize_value((date(2026, 1, 1), date(2026, 1, 2))) == [
        "2026-01-01",
        "2026-01-02",
    ]
    assert serialize_value({"b", "a"}) == ["a", "b"]
    assert serialize_value(Path("logs/user_actions.log")) == "logs/user_actions.log"
    assert serialize_value({"x": date(2026, 1, 1)}) == {"x": "2026-01-01"}


def test_values_equal_normalizes_types() -> None:
    assert values_equal(date(2026, 7, 13), "2026-07-13")
    assert values_equal(["b", "a"], ["b", "a"])
    assert not values_equal("HKG", "US Domestic")
    assert not values_equal(["A"], ["A", "B"])


_RAW_INPUT_WIDGET_RE = re.compile(
    r"\bst\.(radio|selectbox|multiselect|slider|date_input|text_input|"
    r"number_input|checkbox)\s*\("
)
_ACTION_LOGGER = STREAMLIT_DIR / "dashboard" / "action_logger.py"


def test_no_raw_streamlit_input_widgets_outside_action_logger() -> None:
    """New input widgets must use action_logger wrappers so they are logged."""
    violations: list[str] = []
    for path in sorted((STREAMLIT_DIR / "dashboard").rglob("*.py")):
        if path.resolve() == _ACTION_LOGGER.resolve():
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if _RAW_INPUT_WIDGET_RE.search(line):
                rel = path.relative_to(STREAMLIT_DIR.parent)
                violations.append(f"{rel}:{i}: {line.strip()}")
    assert not violations, (
        "Use action_logger wrappers (al.radio, al.selectbox, ...) instead of "
        "raw st.* input widgets:\n" + "\n".join(violations)
    )
