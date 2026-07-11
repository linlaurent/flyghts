"""Dashboard section: Delay analysis."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from flyghts.reference import get_airline, get_airport

from ..context import DashboardContext

from ..charts import _complete_daily_series, _start_flight_count_axis_at_zero
from ..components import _render_aggrid
from ..data import parse_delay_minutes


def render_delay_analysis(ctx: DashboardContext) -> None:
    dataset_key = ctx.dataset_key
    geo_scope = ctx.geo_scope
    is_us = ctx.is_us
    show_country = ctx.show_country
    df_all = ctx.df_all
    df = ctx.df
    focus_airport = ctx.focus_airport
    focus_lat = ctx.focus_lat
    focus_lon = ctx.focus_lon
    focus_label = ctx.focus_label
    global_mode = ctx.global_mode
    direction = ctx.direction
    start_date = ctx.start_date
    end_date = ctx.end_date
    top_n = ctx.top_n
    airline_col = ctx.airline_col
    total_flights = ctx.total_flights
    cargo_filter = ctx.cargo_filter
    operating_only = ctx.operating_only
    has_cargo = ctx.has_cargo
    has_operating = ctx.has_operating

    st.header("Delay analysis")
    if global_mode:
        st.caption("Analyzing arrival delays for all US domestic flights")
    else:
        st.caption(f"Analyzing arrival delays for flights involving {focus_label}")

    df_delay = df.copy()
    df_delay["delay_min"] = df_delay["status"].apply(parse_delay_minutes)

    n_total = len(df_delay)
    df_with_delay = df_delay.dropna(subset=["delay_min"])
    n_arrived = len(df_with_delay)
    n_cancelled = n_total - n_arrived
    n_on_time = int((df_with_delay["delay_min"] == 0).sum())
    n_delayed = int((df_with_delay["delay_min"] > 0).sum())
    avg_delay_val = df_with_delay.loc[
        df_with_delay["delay_min"] > 0, "delay_min"
    ].mean()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        on_time_pct = 100 * n_on_time / n_arrived if n_arrived > 0 else 0
        st.metric("On-time (%)", f"{on_time_pct:.1f}%")
    with c2:
        delayed_pct = 100 * n_delayed / n_arrived if n_arrived > 0 else 0
        st.metric("Delayed (%)", f"{delayed_pct:.1f}%")
    with c3:
        st.metric("Cancelled / diverted", f"{n_cancelled:,}")
    with c4:
        st.metric(
            "Avg delay (when late)",
            f"{avg_delay_val:.0f} min" if not pd.isna(avg_delay_val) else "N/A",
        )

    # ── Delay distribution ──
    st.subheader("Delay distribution")
    delayed_flights = df_with_delay[df_with_delay["delay_min"] > 0]
    if not delayed_flights.empty:
        fig_delay_hist = px.histogram(
            delayed_flights,
            x="delay_min",
            nbins=50,
            labels={"delay_min": "Delay (minutes)", "count": "Flights"},
        )
        fig_delay_hist.update_layout(height=350, showlegend=False)
        _start_flight_count_axis_at_zero(fig_delay_hist, "y")
        st.plotly_chart(fig_delay_hist, width="stretch")
    else:
        st.caption("No delayed flights in the selected filters.")

    # ── On-time performance by airline ──
    st.subheader("On-time performance by airline")
    airline_delay = (
        df_with_delay.groupby(airline_col)["delay_min"]
        .agg(
            total="count",
            on_time=lambda x: int((x == 0).sum()),
            avg_delay=lambda x: x[x > 0].mean(),
            delayed_15=lambda x: int((x >= 15).sum()),
        )
        .reset_index()
    )
    airline_delay.columns = [
        airline_col,
        "Total",
        "On-time",
        "Avg delay (min)",
        "Delayed 15+ min",
    ]
    airline_delay["On-time (%)"] = (
        100 * airline_delay["On-time"] / airline_delay["Total"]
    ).round(1)
    airline_delay = airline_delay.sort_values("Total", ascending=False).head(top_n)
    airline_delay["Airline"] = airline_delay[airline_col].apply(
        lambda c: get_airline(c).name if get_airline(c) else c
    )

    if not airline_delay.empty:
        plot_df = airline_delay.sort_values("On-time (%)", ascending=True)
        fig_otp = px.bar(
            plot_df,
            x="On-time (%)",
            y="Airline",
            orientation="h",
            color="On-time (%)",
            color_continuous_scale="RdYlGn",
            range_color=[50, 100],
            text=plot_df["On-time (%)"].apply(lambda x: f"{x}%"),
            custom_data=["Total", "Avg delay (min)"],
        )
        fig_otp.update_traces(
            textposition="outside",
            hovertemplate="%{y}<br>On-time: %{x}%<br>Total flights: %{customdata[0]:,}<br>Avg delay: %{customdata[1]:.0f} min<extra></extra>",
        )
        fig_otp.update_layout(height=320, showlegend=False)
        st.plotly_chart(fig_otp, width="stretch")

    # ── Average delay by hour ──
    st.subheader("Average delay by hour of day")
    if "scheduled_time" in df_with_delay.columns:
        df_hour_delay = df_with_delay.copy()
        df_hour_delay["hour"] = pd.to_datetime(
            df_hour_delay["scheduled_time"], errors="coerce"
        ).dt.hour
        df_hour_delay = df_hour_delay.dropna(subset=["hour"])
        by_hour_d = (
            df_hour_delay.groupby("hour")["delay_min"]
            .agg(
                avg_delay="mean",
                on_time_pct=lambda x: 100 * (x == 0).sum() / len(x),
                total="count",
            )
            .reset_index()
        )
        by_hour_d.columns = ["Hour", "Avg delay (min)", "On-time (%)", "Total"]
        if not by_hour_d.empty:
            fig_hour_delay = go.Figure()
            fig_hour_delay.add_trace(
                go.Bar(
                    x=by_hour_d["Hour"],
                    y=by_hour_d["Avg delay (min)"],
                    name="Avg delay (min)",
                )
            )
            fig_hour_delay.add_trace(
                go.Scatter(
                    x=by_hour_d["Hour"],
                    y=by_hour_d["On-time (%)"],
                    name="On-time (%)",
                    yaxis="y2",
                    line=dict(color="#ff7f0e"),
                    mode="lines",
                )
            )
            fig_hour_delay.update_layout(
                height=350,
                xaxis=dict(title="Hour of day"),
                yaxis=dict(title="Avg delay (min)", side="left"),
                yaxis2=dict(
                    title="On-time (%)",
                    side="right",
                    overlaying="y",
                    range=[0, 100],
                ),
                legend=dict(x=1.1, xanchor="left"),
            )
            st.plotly_chart(fig_hour_delay, width="stretch")

    # ── On-time performance over time ──
    st.subheader("On-time performance over time")
    delay_by_date = (
        df_with_delay.groupby(df_with_delay["date"].dt.date)["delay_min"]
        .agg(
            on_time_pct=lambda x: 100 * (x == 0).sum() / len(x),
            avg_delay="mean",
            total="count",
        )
        .reset_index()
    )
    delay_by_date.columns = ["Date", "On-time (%)", "Avg delay (min)", "Total"]
    delay_by_date = _complete_daily_series(
        delay_by_date,
        date_col="Date",
        value_cols=["On-time (%)", "Avg delay (min)", "Total"],
        start_date=start_date,
        end_date=end_date,
    )
    if not delay_by_date.empty:
        fig_delay_time = go.Figure()
        fig_delay_time.add_trace(
            go.Scatter(
                x=delay_by_date["Date"],
                y=delay_by_date["On-time (%)"],
                name="On-time (%)",
                line=dict(color="#2ca02c"),
                mode="lines",
            )
        )
        fig_delay_time.add_trace(
            go.Scatter(
                x=delay_by_date["Date"],
                y=delay_by_date["Avg delay (min)"],
                name="Avg delay (min)",
                yaxis="y2",
                line=dict(color="#d62728"),
                mode="lines",
            )
        )
        fig_delay_time.update_layout(
            height=350,
            xaxis=dict(title="Date"),
            yaxis=dict(title="On-time (%)", side="left", range=[0, 100]),
            yaxis2=dict(
                title="Avg delay (min)",
                side="right",
                overlaying="y",
            ),
            legend=dict(x=1.1, xanchor="left"),
        )
        st.plotly_chart(fig_delay_time, width="stretch")
