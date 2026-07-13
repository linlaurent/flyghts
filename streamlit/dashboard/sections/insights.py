"""Dashboard section: Insights."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from flyghts.reference import get_airline, get_airport

from ..context import DashboardContext

from flyghts.insights import (
    DEFAULT_COMPANY_AIRLINE_COL,
    DEFAULT_MIN_ABSOLUTE_CHANGE_PER_DAY,
    DEFAULT_MIN_PERCENT_CHANGE,
    DEFAULT_MIN_PREVIOUS_FLIGHTS,
    MARKETING_AIRLINE_COL,
    available_period_labels,
    compare_periods,
)

from ..charts import _start_flight_count_axis_at_zero
from ..components import _render_aggrid, _render_insight_grid
from ..formatting import (
    ALLIANCE_ORDER,
    _alliance_label,
    _airline_label,
    with_alliance_column,
)
from ..insight_ui import (
    _comparison_period_options,
    _default_current_period_index,
    _render_insight_chart,
    _render_insight_route_map,
    _slice_period,
)


def render_insights(ctx: DashboardContext) -> None:
    st.header("Periodic insights")
    st.caption("Compare any two weeks or months using the current filters.")

    if ctx.df.empty:
        st.info("No flight data available for the selected filters.")
        return

    ctl_kind, ctl_current, ctl_comparison = st.columns(3)
    with ctl_kind:
        period_label = st.selectbox(
            "Period type",
            options=["Weekly", "Monthly"],
            index=1,
            key="insights_period_kind",
        )
        period_kind = "weekly" if period_label == "Weekly" else "monthly"
        period_options = available_period_labels(ctx.df, period_kind)
        if len(period_options) < 2:
            st.info("At least two periods are required for insights.")
            return
    with ctl_current:
        current_period = st.selectbox(
            "Current period",
            options=period_options,
            index=_default_current_period_index(period_options),
            key="insights_current_period",
            help="Defaults to the period before the latest available period because the latest period may be incomplete.",
        )
    comparison_options, comparison_default_idx = _comparison_period_options(
        period_options, current_period
    )
    with ctl_comparison:
        comparison_period = st.selectbox(
            "Compare with",
            options=comparison_options,
            index=comparison_default_idx,
            key="insights_comparison_period",
            help="Defaults to the same-frequency period immediately before the selected current period.",
        )

    insights_airline_col = (
        ctx.airline_col
        if ctx.airline_col in ctx.df.columns
        else (
            DEFAULT_COMPANY_AIRLINE_COL
            if DEFAULT_COMPANY_AIRLINE_COL in ctx.df.columns
            else MARKETING_AIRLINE_COL
        )
    )
    bidirectional_focus_airport = (
        ctx.focus_airport if ctx.direction == "Both" and ctx.focus_airport else None
    )

    ctl_baseline, ctl_abs, ctl_pct = st.columns(3)
    with ctl_baseline:
        min_previous_flights = st.number_input(
            "Minimum comparison flights",
            min_value=1,
            max_value=10_000,
            value=DEFAULT_MIN_PREVIOUS_FLIGHTS,
            step=1,
            help="Ignore frequency changes on very small baseline routes.",
            key="insights_min_previous_flights",
        )
    with ctl_abs:
        min_absolute_change = st.number_input(
            "Minimum change per day",
            min_value=0.1,
            max_value=1000.0,
            value=DEFAULT_MIN_ABSOLUTE_CHANGE_PER_DAY,
            step=0.1,
            help="Required normalized flights-per-day change.",
            key="insights_min_absolute_change",
        )
    with ctl_pct:
        min_percent_change = st.number_input(
            "Minimum percent change",
            min_value=1.0,
            max_value=100.0,
            value=DEFAULT_MIN_PERCENT_CHANGE,
            step=1.0,
            help="Required relative change from the comparison period.",
            key="insights_min_percent_change",
        )

    try:
        insights = compare_periods(
            ctx.df,
            period_kind=period_kind,
            current_period=current_period,
            comparison_period=comparison_period,
            airline_col=insights_airline_col,
            bidirectional_focus_airport=bidirectional_focus_airport,
            min_previous_flights=int(min_previous_flights),
            min_absolute_change_per_day=float(min_absolute_change),
            min_percent_change=float(min_percent_change),
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    prev_label = (
        f"{insights.previous.label} ({insights.previous.observed_days} observed days)"
    )
    curr_label = (
        f"{insights.current.label} ({insights.current.observed_days} observed days)"
    )
    st.caption(f"Comparison: {prev_label} / Current: {curr_label}")

    m1, m2, m3, m4, m5, m6, m7, m8 = st.columns(8)
    with m1:
        st.metric(
            "Current flights",
            f"{insights.current_total_flights:,}",
            delta=insights.current_total_flights - insights.previous_total_flights,
        )
    with m2:
        st.metric("New companies", f"{len(insights.new_companies):,}")
    with m3:
        st.metric("Disappeared companies", f"{len(insights.disappeared_companies):,}")
    with m4:
        st.metric("New routes", f"{len(insights.new_routes):,}")
    with m5:
        st.metric("Disappeared routes", f"{len(insights.disappeared_routes):,}")
    with m6:
        st.metric("Large drops", f"{len(insights.frequency_drops):,}")

    # OPTD alliance presence in each period (members only; not from code-shares)
    df_prev_a = with_alliance_column(
        _slice_period(ctx.df, insights.previous), insights_airline_col
    )
    df_curr_a = with_alliance_column(
        _slice_period(ctx.df, insights.current), insights_airline_col
    )
    prev_alliances = (
        set(df_prev_a["alliance"].unique()) if not df_prev_a.empty else set()
    )
    curr_alliances = (
        set(df_curr_a["alliance"].unique()) if not df_curr_a.empty else set()
    )
    new_alliance_ids = sorted(curr_alliances - prev_alliances)
    disappeared_alliance_ids = sorted(prev_alliances - curr_alliances)
    with m7:
        st.metric("New alliances", f"{len(new_alliance_ids):,}")
    with m8:
        st.metric("Disappeared alliances", f"{len(disappeared_alliance_ids):,}")

    insight_tabs = st.tabs(
        [
            "Routes",
            "Companies",
            "Alliances",
            "Company-routes",
            "Frequency changes",
        ]
    )

    with insight_tabs[1]:
        chart_new_companies, chart_disappeared_companies = st.columns(2)
        with chart_new_companies:
            _render_insight_chart(
                "New companies by current flights",
                insights.new_companies,
                value_col="current_flights",
                value_label="Current flights",
                color_scale="Blues",
                empty_message="No companies appeared for the first time in this period.",
                top_n=ctx.top_n,
            )
        with chart_disappeared_companies:
            _render_insight_chart(
                "Disappeared companies by comparison flights",
                insights.disappeared_companies,
                value_col="previous_flights",
                value_label="Previous flights",
                color_scale="Oranges",
                empty_message="No companies disappeared in this period.",
                top_n=ctx.top_n,
            )
        st.caption("Company-only insights do not have route maps.")
        table_new_companies, table_disappeared_companies = st.columns(2)
        with table_new_companies:
            _render_insight_grid(
                "New companies",
                insights.new_companies,
                "No companies appeared for the first time in this period.",
            )
        with table_disappeared_companies:
            _render_insight_grid(
                "Disappeared companies",
                insights.disappeared_companies,
                "No companies disappeared in this period.",
            )

    with insight_tabs[2]:
        st.caption(
            "Alliance membership from OpenTravelData (OPTD members only). "
            "Not inferred from code-shares."
        )
        curr_counts = (
            df_curr_a["alliance"].value_counts()
            if not df_curr_a.empty
            else pd.Series(dtype=int)
        )
        prev_counts = (
            df_prev_a["alliance"].value_counts()
            if not df_prev_a.empty
            else pd.Series(dtype=int)
        )
        alliance_rows = []
        for alliance_id in ALLIANCE_ORDER:
            cur = int(curr_counts.get(alliance_id, 0))
            prev = int(prev_counts.get(alliance_id, 0))
            if cur == 0 and prev == 0:
                continue
            alliance_rows.append(
                {
                    "Alliance": _alliance_label(alliance_id),
                    "Previous flights": prev,
                    "Current flights": cur,
                    "Change": cur - prev,
                }
            )
        alliance_period_df = pd.DataFrame(alliance_rows)
        if not alliance_period_df.empty:
            fig_alliance_period = px.bar(
                alliance_period_df.sort_values("Current flights", ascending=True),
                x="Current flights",
                y="Alliance",
                orientation="h",
                color="Current flights",
                color_continuous_scale="Teal",
                hover_data=["Previous flights", "Change"],
            )
            fig_alliance_period.update_layout(height=320, showlegend=False)
            _start_flight_count_axis_at_zero(fig_alliance_period, "x")
            st.plotly_chart(fig_alliance_period, width="stretch")
            _render_aggrid(alliance_period_df)
        else:
            st.caption("No alliance traffic in the selected periods.")

        new_all_df = pd.DataFrame(
            [
                {
                    "Alliance": _alliance_label(a),
                    "current_flights": int(curr_counts.get(a, 0)),
                }
                for a in new_alliance_ids
            ]
        )
        disappeared_all_df = pd.DataFrame(
            [
                {
                    "Alliance": _alliance_label(a),
                    "previous_flights": int(prev_counts.get(a, 0)),
                }
                for a in disappeared_alliance_ids
            ]
        )
        # Adapt for insight chart which expects airline column naming
        if not new_all_df.empty:
            new_all_df = new_all_df.rename(columns={"Alliance": "airline"})
        if not disappeared_all_df.empty:
            disappeared_all_df = disappeared_all_df.rename(
                columns={"Alliance": "airline"}
            )

        chart_new_all, chart_dis_all = st.columns(2)
        with chart_new_all:
            _render_insight_chart(
                "New alliances by current flights",
                new_all_df,
                value_col="current_flights",
                value_label="Current flights",
                color_scale="Blues",
                empty_message="No alliances appeared for the first time in this period.",
                top_n=ctx.top_n,
            )
        with chart_dis_all:
            _render_insight_chart(
                "Disappeared alliances by comparison flights",
                disappeared_all_df,
                value_col="previous_flights",
                value_label="Previous flights",
                color_scale="Oranges",
                empty_message="No alliances disappeared in this period.",
                top_n=ctx.top_n,
            )

        # Member airlines driving current-period alliance traffic
        st.subheader("Member airlines in current period (by alliance)")
        if df_curr_a.empty:
            st.caption("No flights in the current period.")
        else:
            member_rows = (
                df_curr_a.groupby(["alliance", insights_airline_col])
                .size()
                .reset_index(name="Flights")
                .sort_values("Flights", ascending=False)
            )
            member_rows["Alliance"] = member_rows["alliance"].map(_alliance_label)
            member_rows["Airline"] = member_rows[insights_airline_col].apply(
                _airline_label
            )
            _render_aggrid(
                member_rows[["Alliance", "Airline", "Flights"]].head(
                    max(ctx.top_n * 4, 20)
                )
            )

    with insight_tabs[0]:
        chart_new_routes, chart_disappeared_routes = st.columns(2)
        with chart_new_routes:
            _render_insight_chart(
                "New routes by current flights",
                insights.new_routes,
                value_col="current_flights",
                value_label="Current flights",
                color_scale="Greens",
                empty_message="No routes appeared for the first time in this period.",
                top_n=ctx.top_n,
            )
        with chart_disappeared_routes:
            _render_insight_chart(
                "Disappeared routes by comparison flights",
                insights.disappeared_routes,
                value_col="previous_flights",
                value_label="Previous flights",
                color_scale="Oranges",
                empty_message="No routes disappeared in this period.",
                top_n=ctx.top_n,
            )
        map_new_routes, map_disappeared_routes = st.columns(2)
        with map_new_routes:
            _render_insight_route_map(
                "New routes",
                ctx.df,
                insights.new_routes,
                insights.current,
                airline_col=insights_airline_col,
                bidirectional_focus_airport=bidirectional_focus_airport,
                global_mode=ctx.global_mode,
                direction=ctx.direction,
                focus_airport=ctx.focus_airport,
                focus_lat=ctx.focus_lat,
                focus_lon=ctx.focus_lon,
                geo_scope=ctx.geo_scope,
                top_routes_n=ctx.top_n,
            )
        with map_disappeared_routes:
            _render_insight_route_map(
                "Disappeared routes",
                ctx.df,
                insights.disappeared_routes,
                insights.previous,
                airline_col=insights_airline_col,
                bidirectional_focus_airport=bidirectional_focus_airport,
                global_mode=ctx.global_mode,
                direction=ctx.direction,
                focus_airport=ctx.focus_airport,
                focus_lat=ctx.focus_lat,
                focus_lon=ctx.focus_lon,
                geo_scope=ctx.geo_scope,
                top_routes_n=ctx.top_n,
            )
        table_new_routes, table_disappeared_routes = st.columns(2)
        with table_new_routes:
            _render_insight_grid(
                "New routes",
                insights.new_routes,
                "No routes appeared for the first time in this period.",
            )
        with table_disappeared_routes:
            _render_insight_grid(
                "Disappeared routes",
                insights.disappeared_routes,
                "No routes disappeared in this period.",
            )

    with insight_tabs[3]:
        chart_new_company_routes, chart_disappeared_company_routes = st.columns(2)
        with chart_new_company_routes:
            _render_insight_chart(
                "New company-routes by current flights",
                insights.new_company_routes,
                value_col="current_flights",
                value_label="Current flights",
                color_scale="Greens",
                empty_message="No company-specific routes appeared for the first time.",
                top_n=ctx.top_n,
            )
        with chart_disappeared_company_routes:
            _render_insight_chart(
                "Disappeared company-routes by comparison flights",
                insights.disappeared_company_routes,
                value_col="previous_flights",
                value_label="Previous flights",
                color_scale="Oranges",
                empty_message="No company-specific routes disappeared.",
                top_n=ctx.top_n,
            )
        map_new_company_routes, map_disappeared_company_routes = st.columns(2)
        with map_new_company_routes:
            _render_insight_route_map(
                "New routes by company",
                ctx.df,
                insights.new_company_routes,
                insights.current,
                airline_col=insights_airline_col,
                bidirectional_focus_airport=bidirectional_focus_airport,
                global_mode=ctx.global_mode,
                direction=ctx.direction,
                focus_airport=ctx.focus_airport,
                focus_lat=ctx.focus_lat,
                focus_lon=ctx.focus_lon,
                geo_scope=ctx.geo_scope,
                top_routes_n=ctx.top_n,
            )
        with map_disappeared_company_routes:
            _render_insight_route_map(
                "Disappeared routes by company",
                ctx.df,
                insights.disappeared_company_routes,
                insights.previous,
                airline_col=insights_airline_col,
                bidirectional_focus_airport=bidirectional_focus_airport,
                global_mode=ctx.global_mode,
                direction=ctx.direction,
                focus_airport=ctx.focus_airport,
                focus_lat=ctx.focus_lat,
                focus_lon=ctx.focus_lon,
                geo_scope=ctx.geo_scope,
                top_routes_n=ctx.top_n,
            )
        table_new_company_routes, table_disappeared_company_routes = st.columns(2)
        with table_new_company_routes:
            _render_insight_grid(
                "New routes by company",
                insights.new_company_routes,
                "No company-specific routes appeared for the first time.",
            )
        with table_disappeared_company_routes:
            _render_insight_grid(
                "Disappeared routes by company",
                insights.disappeared_company_routes,
                "No company-specific routes disappeared in this period.",
            )

    with insight_tabs[4]:
        frequency_metric = st.radio(
            "Frequency change metric",
            options=["Change/day", "Change (%)"],
            index=0,
            horizontal=True,
            help="Rank frequency changes by normalized flights per day or relative percent change.",
            key="insights_frequency_metric",
        )
        frequency_value_col = (
            "percent_change"
            if frequency_metric == "Change (%)"
            else "absolute_change_per_day"
        )
        chart_frequency_increases_left, chart_frequency_drops_right = st.columns(2)
        with chart_frequency_increases_left:
            _render_insight_chart(
                "Largest frequency increases",
                insights.frequency_increases,
                value_col=frequency_value_col,
                value_label=frequency_metric,
                color_scale="Greens",
                empty_message="No routes crossed the increase thresholds.",
                top_n=ctx.top_n,
            )
        with chart_frequency_drops_right:
            _render_insight_chart(
                "Largest frequency drops",
                insights.frequency_drops,
                value_col=frequency_value_col,
                value_label=frequency_metric,
                color_scale="Reds_r",
                empty_message="No routes crossed the drop thresholds.",
                top_n=ctx.top_n,
                ascending=True,
            )
        map_frequency_increases_left, map_frequency_drops_right = st.columns(2)
        with map_frequency_increases_left:
            _render_insight_route_map(
                "Frequency increases",
                ctx.df,
                insights.frequency_increases,
                insights.current,
                airline_col=insights_airline_col,
                bidirectional_focus_airport=bidirectional_focus_airport,
                global_mode=ctx.global_mode,
                direction=ctx.direction,
                focus_airport=ctx.focus_airport,
                focus_lat=ctx.focus_lat,
                focus_lon=ctx.focus_lon,
                geo_scope=ctx.geo_scope,
                top_routes_n=ctx.top_n,
            )
        with map_frequency_drops_right:
            _render_insight_route_map(
                "Frequency drops",
                ctx.df,
                insights.frequency_drops,
                insights.current,
                airline_col=insights_airline_col,
                bidirectional_focus_airport=bidirectional_focus_airport,
                global_mode=ctx.global_mode,
                direction=ctx.direction,
                focus_airport=ctx.focus_airport,
                focus_lat=ctx.focus_lat,
                focus_lon=ctx.focus_lon,
                geo_scope=ctx.geo_scope,
                top_routes_n=ctx.top_n,
            )
        table_frequency_increases_left, table_frequency_drops_right = st.columns(2)
        with table_frequency_increases_left:
            _render_insight_grid(
                "Frequency increases",
                insights.frequency_increases,
                "No routes crossed the configured increase thresholds.",
            )
        with table_frequency_drops_right:
            _render_insight_grid(
                "Frequency drops",
                insights.frequency_drops,
                "No routes crossed the configured drop thresholds.",
            )
