"""Shared dashboard state passed to section renderers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class DashboardContext:
    section: str
    dataset_key: str
    geo_scope: str
    is_us: bool
    show_country: bool
    df_all: pd.DataFrame
    df: pd.DataFrame
    focus_airport: str | None
    focus_lat: float
    focus_lon: float
    focus_label: str
    global_mode: bool
    direction: str
    start_date: date
    end_date: date
    top_n: int
    airline_col: str
    total_flights: int
    cargo_filter: str | None
    operating_only: bool
    has_cargo: bool
    has_operating: bool
    min_date: date
    max_date: date
