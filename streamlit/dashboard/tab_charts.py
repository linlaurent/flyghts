"""Shared temporal tab charts for airline and route deep dives."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from .charts import _complete_daily_series, _start_flight_count_axis_at_zero
from .components import _render_aggrid
from .context import DashboardContext

_WEEKDAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def render_primary_flights_over_time(slice_df: pd.DataFrame, ctx: DashboardContext) -> bool:
    """Dual-axis flights + share chart. Returns True when chart rendered."""
    by_date = (
        slice_df.groupby(slice_df["date"].dt.date).size().reset_index(name="Flights")
    )
    by_date.columns = ["Date", "Flights"]
    if by_date.empty:
        st.caption("No date data.")
        return False

    total_by_date = (
        ctx.df.groupby(ctx.df["date"].dt.date).size().reset_index(name="Total")
    )
    total_by_date.columns = ["Date", "Total"]
    share_df = by_date.merge(total_by_date, on="Date", how="left")
    share_df["Share"] = (100 * share_df["Flights"] / share_df["Total"]).fillna(0)
    share_df = _complete_daily_series(
        share_df,
        date_col="Date",
        value_cols=["Flights", "Total", "Share"],
        start_date=ctx.start_date,
        end_date=ctx.end_date,
    )

    fig_time = go.Figure()
    fig_time.add_trace(
        go.Scatter(
            x=share_df["Date"],
            y=share_df["Flights"],
            name="Flights",
            line=dict(color="#1f77b4"),
            mode="lines",
        )
    )
    fig_time.add_trace(
        go.Scatter(
            x=share_df["Date"],
            y=share_df["Share"],
            name="Share of traffic (%)",
            yaxis="y2",
            line=dict(color="#ff7f0e"),
            mode="lines",
        )
    )
    fig_time.update_layout(
        height=350,
        xaxis=dict(title="Date"),
        yaxis=dict(title="Number of flights", side="left"),
        yaxis2=dict(
            title="Share of traffic (%)",
            side="right",
            overlaying="y",
            range=[0, 100],
        ),
        legend=dict(x=1.1, xanchor="left"),
    )
    _start_flight_count_axis_at_zero(fig_time, "y")
    st.plotly_chart(fig_time, width="stretch")
    return True


def render_secondary_grouped_over_time(
    slice_df: pd.DataFrame,
    ctx: DashboardContext,
    *,
    group_values: pd.Series,
    top_groups: set[str],
    group_key_col: str,
    label_fn: Callable[[str], str],
    color_col: str,
    title: str,
    totals: pd.DataFrame | pd.Series,
    totals_merge: Literal["group", "date"] = "group",
) -> None:
    """Render a daily flight-count line chart split by a top-N group dimension."""
    if not top_groups:
        return

    work = slice_df.copy()
    work[group_key_col] = group_values.values
    by_date_group = (
        work.groupby([work["date"].dt.date, group_key_col])
        .size()
        .reset_index(name="Flights")
    )
    by_date_group.columns = ["Date", group_key_col, "Flights"]
    by_date_group = by_date_group[by_date_group[group_key_col].isin(top_groups)]

    if totals_merge == "date":
        by_date_group = by_date_group.merge(
            totals,
            left_on="Date",
            right_index=True,
            how="left",
        )
    else:
        by_date_group = by_date_group.merge(
            totals,
            on=["Date", group_key_col],
            how="left",
        )

    by_date_group[color_col] = by_date_group[group_key_col].apply(label_fn)
    by_date_group = _complete_daily_series(
        by_date_group,
        date_col="Date",
        value_cols=["Flights", "Total"],
        start_date=ctx.start_date,
        end_date=ctx.end_date,
        group_cols=[group_key_col, color_col],
    )
    if by_date_group.empty:
        return

    fig = px.line(
        by_date_group,
        x="Date",
        y="Flights",
        color=color_col,
        labels={"Flights": "Number of flights"},
        custom_data=["Total", color_col],
    )
    fig.update_traces(
        hovertemplate=(
            "%{customdata[1]}<br>%{x}<br>Flights: %{y:,}"
            "<br>Total (denom): %{customdata[0]:,}<extra></extra>"
        ),
    )
    fig.update_layout(height=350, title=title)
    _start_flight_count_axis_at_zero(fig, "y")
    st.plotly_chart(fig, width="stretch")


def render_scheduled_hour(slice_df: pd.DataFrame, ctx: DashboardContext) -> None:
    """Bar chart of flights by scheduled hour of day."""
    if not ctx.global_mode:
        st.caption(
            f"Departure time for flights from {ctx.focus_airport}; "
            f"arrival time for flights to {ctx.focus_airport}."
        )
    if "scheduled_time" not in slice_df.columns:
        st.caption("No scheduled_time column in data.")
        return

    hour_df = slice_df.dropna(subset=["scheduled_time"]).copy()
    hour_df["hour"] = pd.to_datetime(hour_df["scheduled_time"], errors="coerce").dt.hour
    hour_df = hour_df.dropna(subset=["hour"])
    by_hour = hour_df.groupby("hour").size().reset_index(name="Flights")
    if by_hour.empty:
        st.caption("No scheduled time data.")
        return

    fig_hour = px.bar(
        by_hour,
        x="hour",
        y="Flights",
        labels={"hour": "Hour of day", "Flights": "Number of flights"},
    )
    fig_hour.update_layout(height=350)
    _start_flight_count_axis_at_zero(fig_hour, "y")
    st.plotly_chart(fig_hour, width="stretch")


def render_weekday_average(slice_df: pd.DataFrame) -> None:
    """Bar chart of average flights per weekday."""
    weekday_df = slice_df.copy()
    weekday_df["weekday"] = weekday_df["date"].dt.day_name()
    weekday_total = weekday_df.groupby("weekday").size().rename("Total")
    weekday_dates = (
        weekday_df.groupby("weekday")["date"].apply(lambda s: s.dt.date.nunique()).rename("Days")
    )
    plot_df = pd.concat([weekday_total, weekday_dates], axis=1).reset_index()
    plot_df["Avg"] = (plot_df["Total"] / plot_df["Days"]).round(1)
    plot_df["weekday"] = pd.Categorical(
        plot_df["weekday"], categories=_WEEKDAY_ORDER, ordered=True
    )
    plot_df = plot_df.sort_values("weekday")
    if plot_df.empty:
        st.caption("No date data for weekday analysis.")
        return

    fig_wd = px.bar(
        plot_df,
        x="weekday",
        y="Avg",
        labels={"weekday": "Day of week", "Avg": "Avg flights per day"},
        custom_data=["Total", "Days"],
    )
    fig_wd.update_traces(
        hovertemplate=(
            "%{x}<br>Avg: %{y}<br>Total: %{customdata[0]:,}"
            "<br>Days: %{customdata[1]}<extra></extra>"
        ),
    )
    fig_wd.update_layout(height=350)
    _start_flight_count_axis_at_zero(fig_wd, "y")
    st.plotly_chart(fig_wd, width="stretch")


def render_cargo_tab(slice_df: pd.DataFrame, ctx: DashboardContext) -> None:
    """Cargo vs passenger over time and summary table."""
    if "cargo" not in slice_df.columns:
        st.caption("No cargo column in data.")
        return

    cargo_by_date = (
        slice_df.groupby([slice_df["date"].dt.date, "cargo"])
        .size()
        .reset_index(name="Flights")
    )
    cargo_by_date["Type"] = cargo_by_date["cargo"].map({True: "Cargo", False: "Passenger"})
    cargo_by_date = _complete_daily_series(
        cargo_by_date,
        date_col="date",
        value_cols=["Flights"],
        start_date=ctx.start_date,
        end_date=ctx.end_date,
        group_cols=["cargo", "Type"],
    )
    if not cargo_by_date.empty:
        fig_cargo = px.line(
            cargo_by_date,
            x="date",
            y="Flights",
            color="Type",
            labels={"date": "Date", "Flights": "Number of flights"},
            custom_data=["Type"],
        )
        fig_cargo.update_traces(
            hovertemplate="%{customdata[0]}<br>%{x}<br>Flights: %{y:,}<extra></extra>",
        )
        fig_cargo.update_layout(height=350)
        _start_flight_count_axis_at_zero(fig_cargo, "y")
        st.plotly_chart(fig_cargo, width="stretch")

    summary = pd.DataFrame(
        [
            {"Type": "Passenger", "Flights": int((slice_df["cargo"] == False).sum())},
            {"Type": "Cargo", "Flights": int((slice_df["cargo"] == True).sum())},
        ]
    )
    _render_aggrid(summary)
