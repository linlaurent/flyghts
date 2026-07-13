"""Import-safety tests for the Streamlit dashboard package."""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

STREAMLIT_DIR = Path(__file__).resolve().parent.parent / "streamlit"
PROJECT_ROOT = STREAMLIT_DIR.parent
DASHBOARD_DIR = STREAMLIT_DIR / "dashboard"


def _dashboard_module_names() -> list[str]:
    names: list[str] = []
    for path in sorted((STREAMLIT_DIR / "dashboard").rglob("*.py")):
        rel = path.relative_to(STREAMLIT_DIR).with_suffix("")
        names.append(".".join(rel.parts))
    return names


@pytest.fixture(scope="module", autouse=True)
def _dashboard_import_path() -> Iterator[None]:
    streamlit_path = str(STREAMLIT_DIR)
    inserted = streamlit_path not in sys.path
    if inserted:
        sys.path.insert(0, streamlit_path)
    yield
    if inserted:
        sys.path.remove(streamlit_path)
    for module_name in list(sys.modules):
        if module_name == "dashboard" or module_name.startswith("dashboard."):
            del sys.modules[module_name]


@pytest.mark.parametrize("module_name", _dashboard_module_names())
def test_dashboard_package_modules_import(module_name: str) -> None:
    importlib.import_module(module_name)


def test_dashboard_section_renderers_are_callable() -> None:
    from dashboard.sections import (
        dispatch_section,
        render_airline_dive,
        render_alliance_dive,
        render_delay_analysis,
        render_insights,
        render_overview,
        render_reference_data,
        render_route_dive,
    )

    for renderer in (
        dispatch_section,
        render_overview,
        render_insights,
        render_airline_dive,
        render_alliance_dive,
        render_route_dive,
        render_reference_data,
        render_delay_analysis,
    ):
        assert callable(renderer)


def test_flight_dashboard_entrypoint_imports() -> None:
    entrypoint = STREAMLIT_DIR / "flight_dashboard.py"
    spec = importlib.util.spec_from_file_location("flight_dashboard", entrypoint)
    assert spec is not None and spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


def test_dashboard_has_no_undefined_names() -> None:
    """Catch missing imports (F821) that import-time checks cannot see."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            str(DASHBOARD_DIR),
            "--select",
            "F821",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
