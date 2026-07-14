"""Browse reference airlines, airports, alliances, and coverage gaps."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from flyghts.reference import (
    find_missing_reference_codes,
    list_airlines,
    list_airports,
    list_alliances,
)

from ..components import _render_aggrid
from ..context import DashboardContext
from ..formatting import ALLIANCE_DISPLAY


@st.cache_data(show_spinner=False)
def _airlines_dataframe() -> pd.DataFrame:
    rows = list_airlines()
    return pd.DataFrame(
        [
            {
                "ICAO": a.icao,
                "IATA": a.iata,
                "Name": a.name,
                "Country": a.country,
            }
            for a in rows
        ]
    )


@st.cache_data(show_spinner=False)
def _airports_dataframe() -> pd.DataFrame:
    rows = list_airports()
    return pd.DataFrame(
        [
            {
                "IATA": a.iata,
                "Name": a.name,
                "City": a.city,
                "Country": a.country,
                "Province": a.province,
                "Latitude": a.latitude,
                "Longitude": a.longitude,
            }
            for a in rows
        ]
    )


@st.cache_data(show_spinner=False)
def _alliances_dataframe() -> pd.DataFrame:
    rows = list_alliances(members_only=False)
    return pd.DataFrame(
        [
            {
                "Alliance": ALLIANCE_DISPLAY.get(a.alliance, a.alliance),
                "Type": a.alliance_type,
                "ICAO": a.icao,
                "IATA": a.iata,
                "Name": a.name,
                "From": a.from_date.isoformat() if a.from_date else "",
                "To": a.to_date.isoformat() if a.to_date else "",
            }
            for a in rows
        ]
    )


def _gaps_dataframe(pairs: list[tuple[str, int]]) -> pd.DataFrame:
    return pd.DataFrame([{"Code": code, "Occurrences": count} for code, count in pairs])


def render_reference_data(ctx: DashboardContext) -> None:
    """Render browseable reference tables and dataset coverage gaps."""
    st.subheader("Reference data")
    st.caption(
        "Airlines and airports are static reference tables "
        "(not affected by flight filters). Alliances are OPTD membership "
        "intervals (From/To); empty To means open-ended in OPTD. "
        "Coverage gaps use the full loaded "
        f"{ctx.dataset_key} dataset before date/direction filters."
    )

    tab_airlines, tab_airports, tab_alliances, tab_gaps = st.tabs(
        ["Airlines", "Airports", "Alliances", "Coverage gaps"]
    )

    with tab_airlines:
        airlines_df = _airlines_dataframe()
        st.metric("Airlines", f"{len(airlines_df):,}")
        _render_aggrid(airlines_df, height=520)

    with tab_airports:
        airports_df = _airports_dataframe()
        st.metric("Airports", f"{len(airports_df):,}")
        _render_aggrid(airports_df, height=520)

    with tab_alliances:
        alliances_df = _alliances_dataframe()
        st.metric("Alliance memberships", f"{len(alliances_df):,}")
        st.caption(
            "One row per OPTD membership spell. Empty To = still current in OPTD."
        )
        _render_aggrid(alliances_df, height=520)

    with tab_gaps:
        gaps = find_missing_reference_codes(ctx.df_all)
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric(
                "Unmatched airlines",
                f"{len(gaps.missing_airlines):,} of {gaps.total_airline_codes:,}",
            )
        with col_b:
            st.metric(
                "Unmatched airports",
                f"{len(gaps.missing_airports):,} of {gaps.total_airport_codes:,}",
            )

        st.caption(
            "Codes present in flight data but missing from reference. "
            "Add them to _AIRLINE_OVERRIDES / _AIRPORT_OVERRIDES in the reference module."
        )

        left, right = st.columns(2)
        with left:
            st.markdown("**Missing airlines**")
            if gaps.missing_airlines:
                _render_aggrid(_gaps_dataframe(gaps.missing_airlines), height=420)
            else:
                st.info("All airline codes matched for this dataset.")
        with right:
            st.markdown("**Missing airports**")
            if gaps.missing_airports:
                _render_aggrid(_gaps_dataframe(gaps.missing_airports), height=420)
            else:
                st.info("All airport codes matched for this dataset.")
