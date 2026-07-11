"""Insight section chart and map helpers."""

import pandas as pd
import plotly.express as px
import streamlit as st

from .charts import _start_flight_count_axis_at_zero
from .formatting import _format_insight_table
from .maps import _render_flight_map, _render_network_map


def _default_current_period_index(period_options: list[str]) -> int:
    """Default to the period before the latest one when possible."""
    if len(period_options) >= 2:
        return len(period_options) - 2
    return 0


def _comparison_period_options(
    period_options: list[str], current_period: str
) -> tuple[list[str], int]:
    """Return comparison choices and the default index for the selected period."""
    comparison_options = [p for p in period_options if p != current_period]
    if not comparison_options:
        return [], 0

    current_idx = period_options.index(current_period)
    default_period = (
        period_options[current_idx - 1] if current_idx > 0 else comparison_options[0]
    )
    return comparison_options, comparison_options.index(default_period)


def _render_insight_chart(
    title: str,
    df: pd.DataFrame,
    *,
    value_col: str,
    value_label: str,
    color_scale: str,
    empty_message: str,
    top_n: int,
    ascending: bool = False,
) -> None:
    st.subheader(title)
    if df.empty:
        st.caption(empty_message)
        return

    sorted_df = df.sort_values(value_col, ascending=ascending).head(top_n)
    plot_df = _format_insight_table(sorted_df)
    if value_label not in plot_df.columns:
        plot_df = plot_df.rename(columns={value_col: value_label})
    if {"Airline", "Route"}.issubset(plot_df.columns):
        plot_df["Airline route"] = plot_df["Airline"] + " | " + plot_df["Route"]
        label_col = "Airline route"
    else:
        label_col = "Route" if "Route" in plot_df.columns else "Airline"
    hover_cols = [
        col
        for col in [
            "Airline",
            "Route",
            "Previous flights",
            "Current flights",
            "Change/day",
            "Change (%)",
        ]
        if col in plot_df.columns and col != value_label
    ]
    fig = px.bar(
        plot_df.sort_values(value_label, ascending=ascending),
        x=value_label,
        y=label_col,
        orientation="h",
        color=value_label,
        color_continuous_scale=color_scale,
        hover_data=hover_cols,
    )
    fig.update_layout(
        height=360, yaxis={"categoryorder": "total ascending"}, showlegend=False
    )
    if value_label in {
        "Previous flights",
        "Current flights",
        "Number of flights",
        "Flights",
    }:
        _start_flight_count_axis_at_zero(fig, "x")
    st.plotly_chart(fig, width="stretch")


def _slice_period(df: pd.DataFrame, window) -> pd.DataFrame:
    dates = pd.to_datetime(df["date"]).dt.normalize()
    return df[(dates >= window.start) & (dates <= window.end)]


def _filter_df_for_insight_routes(
    df_period: pd.DataFrame,
    routes_df: pd.DataFrame,
    *,
    airline_col: str,
    bidirectional_focus_airport: str | None,
) -> pd.DataFrame:
    if df_period.empty or routes_df.empty:
        return df_period.iloc[0:0]

    include_airline = (
        "airline" in routes_df.columns and airline_col in df_period.columns
    )
    if bidirectional_focus_airport:
        work = df_period.copy()
        touches_focus = (work["origin"] == bidirectional_focus_airport) | (
            work["destination"] == bidirectional_focus_airport
        )
        counterpart = work["destination"].where(
            work["origin"] == bidirectional_focus_airport,
            work["origin"],
        )
        work["_insight_origin"] = work["origin"].where(
            ~touches_focus, bidirectional_focus_airport
        )
        work["_insight_destination"] = work["destination"].where(
            ~touches_focus, counterpart
        )
        match = (
            routes_df[["origin", "destination"]]
            .drop_duplicates()
            .rename(
                columns={
                    "origin": "_insight_origin",
                    "destination": "_insight_destination",
                }
            )
        )
        keys = ["_insight_origin", "_insight_destination"]
    else:
        work = df_period.copy()
        match = routes_df[["origin", "destination"]].drop_duplicates()
        keys = ["origin", "destination"]

    if include_airline:
        match = routes_df[["airline", "origin", "destination"]].drop_duplicates()
        if bidirectional_focus_airport:
            match = match.rename(
                columns={
                    "airline": airline_col,
                    "origin": "_insight_origin",
                    "destination": "_insight_destination",
                }
            )
            keys = [airline_col, "_insight_origin", "_insight_destination"]
        else:
            match = match.rename(columns={"airline": airline_col})
            keys = [airline_col, "origin", "destination"]

    filtered = work.merge(match, on=keys, how="inner")
    return filtered.drop(
        columns=[
            c
            for c in ["_insight_origin", "_insight_destination"]
            if c in filtered.columns
        ]
    )


def _render_insight_route_map(
    title: str,
    df: pd.DataFrame,
    routes_df: pd.DataFrame,
    window,
    *,
    airline_col: str,
    bidirectional_focus_airport: str | None,
    global_mode: bool,
    direction: str,
    focus_airport: str | None,
    focus_lat: float,
    focus_lon: float,
    geo_scope: str,
    top_routes_n: int,
) -> None:
    st.subheader(title)
    map_period_df = _slice_period(df, window)
    insight_map_df = _filter_df_for_insight_routes(
        map_period_df,
        routes_df,
        airline_col=airline_col,
        bidirectional_focus_airport=bidirectional_focus_airport,
    )
    if insight_map_df.empty:
        st.caption("No route rows are available to map for this insight category.")
        return
    if global_mode:
        _render_network_map(insight_map_df, airline_col, [], geo_scope, top_routes_n)
        return
    if focus_airport is None:
        st.caption("A focus airport is required to render this route map.")
        return
    _render_flight_map(
        insight_map_df,
        direction,
        focus_airport,
        focus_lat,
        focus_lon,
        False,
        [],
        airline_col,
        geo_scope,
        top_arcs_n=top_routes_n,
    )
