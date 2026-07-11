"""
Flight Dashboard - Analyze flight data across multiple datasets.

Supports HKG (Hong Kong International Airport) and US Domestic flight data.
Reads per-date CSVs from data/hkg/ and monthly Parquet files from data/us/.

Features:
- Dataset selector (HKG / US Domestic)
- Two modes for US Domestic:
    - Focus airport: hub-centric view with direction filter and spoke-map
    - Global network: network-wide statistics (top routes, busiest airports,
      network map with airport bubbles + route arcs) and no focus constraint
- Top airlines/destinations, interactive map with multi-airline overlay
- Airline deep dive (top O-D pairs in global mode) and airline comparison
- Route deep dive, delay analysis (US)

Run with: uv run streamlit run streamlit/flight_dashboard.py
"""

import sys
from pathlib import Path

import streamlit as st

_PROJECT_SRC = Path(__file__).resolve().parent.parent / "src"
if _PROJECT_SRC.is_dir() and str(_PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(_PROJECT_SRC))

from dashboard import build_dashboard_context  # noqa: E402
from dashboard.sections import dispatch_section  # noqa: E402


def main() -> None:
    st.set_page_config(
        page_title="Flight Dashboard",
        page_icon="✈️",
        layout="wide",
    )

    ctx = build_dashboard_context()
    if ctx is None:
        return

    dispatch_section(ctx)


if __name__ == "__main__":
    main()
