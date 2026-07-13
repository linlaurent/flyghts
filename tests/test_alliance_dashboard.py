"""Unit tests for OPTD-only alliance join helpers (never from code-shares)."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

STREAMLIT_DIR = Path(__file__).resolve().parent.parent / "streamlit"


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


def test_alliance_id_uses_optd_members_only() -> None:
    from dashboard.formatting import INDEPENDENT_ALLIANCE, _alliance_id

    assert _alliance_id("CPA") == "oneworld"
    assert _alliance_id("DAL") == "skyteam"
    assert _alliance_id("UAL") == "star_alliance"
    # Affiliate (Horizon) must not count as member alliance
    assert _alliance_id("QXE") == INDEPENDENT_ALLIANCE
    assert _alliance_id("ZZQ") == INDEPENDENT_ALLIANCE
    assert _alliance_id("") == INDEPENDENT_ALLIANCE


def test_with_alliance_column_does_not_use_codeshare_pair() -> None:
    """Alliance comes from airline_col ICAO via OPTD, not marketing≠operating."""
    from dashboard.formatting import with_alliance_column

    df = pd.DataFrame(
        {
            "airline": ["CPA", "AAL", "HGB"],
            "operating_airline": ["CPA", "CPA", "HGB"],
        }
    )
    # Even when marketing AAL codeshares on CPA metal, AAL stays oneworld from OPTD
    out = with_alliance_column(df, "airline")
    assert list(out["alliance"]) == ["oneworld", "oneworld", "independent"]

    out_op = with_alliance_column(df, "operating_airline")
    assert list(out_op["alliance"]) == ["oneworld", "oneworld", "independent"]
