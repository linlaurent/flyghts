"""Sidebar controls and dashboard context assembly."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from flyghts.reference import get_airport

from .config import DATASETS
from .context import DashboardContext
from .data import apply_filters, load_flights


def build_dashboard_context() -> DashboardContext | None:
    """Render sidebar controls, page header, and filtered flight context."""
    with st.sidebar:
        st.header("Dataset")
        dataset_key = st.radio(
            "Dataset",
            options=list(DATASETS.keys()),
            index=0,
            label_visibility="collapsed",
        )

    ds = DATASETS[dataset_key]
    geo_scope = ds["scope"]
    is_us = dataset_key == "US Domestic"
    show_country = not is_us

    df_all = load_flights(dataset_key)

    with st.sidebar:
        if is_us:
            st.markdown("---")
            st.header("Mode")
            mode_sel = st.radio(
                "Mode",
                options=["Global network", "Focus airport"],
                index=0,
                label_visibility="collapsed",
            )
            global_mode = mode_sel == "Global network"
        else:
            global_mode = False

        if ds["default_airport"]:
            focus_airport: str | None = ds["default_airport"]
        elif global_mode:
            focus_airport = None
        else:
            airport_traffic = (
                pd.concat(
                    [
                        df_all["origin"].value_counts(),
                        df_all["destination"].value_counts(),
                    ]
                )
                .groupby(level=0)
                .sum()
                .sort_values(ascending=False)
            )
            airport_options: list[str] = []
            airport_display_to_code: dict[str, str] = {}
            for code in airport_traffic.index:
                info = get_airport(code)
                label = f"{code} - {info.city}" if info and info.city else code
                airport_options.append(label)
                airport_display_to_code[label] = code

            st.markdown("---")
            st.header("Focus airport")
            sel_airport_display = st.selectbox(
                "Airport",
                options=airport_options,
                index=0,
                label_visibility="collapsed",
            )
            focus_airport = airport_display_to_code.get(
                sel_airport_display, airport_traffic.index[0]
            )

    if focus_airport:
        focus_info = get_airport(focus_airport)
        focus_lat = focus_info.latitude if focus_info else 0.0
        focus_lon = focus_info.longitude if focus_info else 0.0
        focus_label = (
            f"{focus_airport} ({focus_info.city})"
            if focus_info and focus_info.city
            else focus_airport
        )
    else:
        focus_lat = 0.0
        focus_lon = 0.0
        focus_label = "US Domestic"

    if global_mode:
        st.title("✈️ US Domestic Flight Dashboard")
        st.caption("Analyzing all US domestic flights")
    else:
        st.title(f"✈️ {focus_label} Flight Dashboard")
        st.caption(f"Analyze flight data to/from {focus_label}")

    min_date = df_all["date"].min().date()
    max_date = df_all["date"].max().date()

    with st.sidebar:
        st.markdown("---")
        st.header("Section")
        section_options = [
            "Overview",
            "Insights",
            "Airline deep dive",
            "Alliance deep dive",
            "Route deep dive",
        ]
        if is_us:
            section_options.append("Delay analysis")
        section = st.radio(
            "View",
            options=section_options,
            index=0,
            label_visibility="collapsed",
            key="main_section",
        )
        st.markdown("---")
        st.header("Filters")
        if global_mode:
            direction = "Both"
        else:
            direction = st.radio(
                "Direction",
                options=["Departures", "Arrivals", "Both"],
                index=2,
                help=(
                    f"Departures = from {focus_airport}, "
                    f"Arrivals = to {focus_airport}, "
                    f"Both = all flights involving {focus_airport}"
                ),
            )
        start_date = st.date_input(
            "Start date",
            value=min_date,
            min_value=min_date,
            max_value=max_date,
        )
        end_date = st.date_input(
            "End date",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
        )
        top_n = st.slider("Top N for rankings", min_value=5, max_value=50, value=10)

        has_cargo = "cargo" in df_all.columns
        if has_cargo and not is_us:
            cargo_filter = st.radio(
                "Flight type",
                options=["All", "Passenger only", "Cargo only"],
                index=1,
                help="Filter by passenger vs cargo flights",
            )
        elif is_us:
            cargo_filter = "Passenger only"
        else:
            cargo_filter = None

        has_operating = "operating_airline" in df_all.columns
        if has_operating:
            operating_only = st.checkbox(
                "Operating carrier only",
                value=True,
                help="Exclude code-share duplicates; show one row per physical flight",
            )
        else:
            operating_only = False

    if start_date > end_date:
        st.error("Start date must be before or equal to end date.")
        return None

    df = apply_filters(
        df_all,
        direction,
        focus_airport,
        pd.Timestamp(start_date),
        pd.Timestamp(end_date),
        cargo_filter=cargo_filter if has_cargo else None,
        operating_only=operating_only if has_operating else False,
    )
    total_flights = len(df)

    st.metric("Total flights (filtered)", f"{total_flights:,}")

    airline_col = (
        "operating_airline" if (operating_only and has_operating) else "airline"
    )

    return DashboardContext(
        section=section,
        dataset_key=dataset_key,
        geo_scope=geo_scope,
        is_us=is_us,
        show_country=show_country,
        df_all=df_all,
        df=df,
        focus_airport=focus_airport,
        focus_lat=focus_lat,
        focus_lon=focus_lon,
        focus_label=focus_label,
        global_mode=global_mode,
        direction=direction,
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        airline_col=airline_col,
        total_flights=total_flights,
        cargo_filter=cargo_filter,
        operating_only=operating_only,
        has_cargo=has_cargo,
        has_operating=has_operating,
        min_date=min_date,
        max_date=max_date,
    )
