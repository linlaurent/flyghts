"""Alliance comparison deep dive."""

import pandas as pd
import plotly.express as px
import streamlit as st

from ...charts import _complete_daily_series, _start_flight_count_axis_at_zero
from ...components import _render_aggrid
from ...context import DashboardContext
from ...data import get_destination_column
from ...formatting import ALLIANCE_ORDER, _alliance_label
from ...maps import _render_flight_map, _render_network_map


def render_alliance_comparison(ctx: DashboardContext, *, df_all: pd.DataFrame) -> None:
    st.header("Alliance comparison")
    present = [a for a in ALLIANCE_ORDER if int((df_all["alliance"] == a).sum()) > 0]
    if len(present) < 2:
        st.info("Need at least two alliances with flights to compare.")
        return

    display_options = [_alliance_label(a) for a in present]
    display_to_id = {_alliance_label(a): a for a in present}
    sel = st.multiselect(
        "Select alliances to compare",
        options=display_options,
        default=[],
        help="Pick 2 or more alliances.",
        key="alliance_cmp_select",
    )
    cmp_ids = [display_to_id[d] for d in sel if d in display_to_id]
    if len(cmp_ids) < 2:
        st.info("Select at least 2 alliances to compare.")
        return

    summary_rows = []
    for alliance_id in cmp_ids:
        df_a = df_all[df_all["alliance"] == alliance_id]
        n = len(df_a)
        share = 100 * n / ctx.total_flights if ctx.total_flights > 0 else 0
        n_dests = get_destination_column(
            df_a, ctx.direction, ctx.focus_airport
        ).nunique()
        summary_rows.append(
            {
                "Alliance": _alliance_label(alliance_id),
                "Flights": n,
                "Share (%)": round(share, 1),
                "Airlines": df_a[ctx.airline_col].nunique(),
                "Destinations": n_dests,
            }
        )
    _render_aggrid(pd.DataFrame(summary_rows))

    df_cmp = df_all[df_all["alliance"].isin(cmp_ids)].copy()
    df_cmp["Alliance"] = df_cmp["alliance"].map(_alliance_label)

    tab_time, tab_share, tab_map = st.tabs(
        ["Flights over time", "Share of traffic over time", "Interactive map"]
    )

    with tab_time:
        by_date = (
            df_cmp.groupby([df_cmp["date"].dt.date, "Alliance"])
            .size()
            .reset_index(name="Flights")
        )
        by_date.columns = ["Date", "Alliance", "Flights"]
        by_date = _complete_daily_series(
            by_date,
            date_col="Date",
            value_cols=["Flights"],
            start_date=ctx.start_date,
            end_date=ctx.end_date,
            group_cols=["Alliance"],
        )
        if not by_date.empty:
            fig = px.line(
                by_date,
                x="Date",
                y="Flights",
                color="Alliance",
                labels={"Flights": "Number of flights"},
            )
            fig.update_layout(height=350)
            _start_flight_count_axis_at_zero(fig, "y")
            st.plotly_chart(fig, width="stretch")

    with tab_share:
        by_date = (
            df_cmp.groupby([df_cmp["date"].dt.date, "Alliance"])
            .size()
            .reset_index(name="Flights")
        )
        by_date.columns = ["Date", "Alliance", "Flights"]
        totals = df_all.groupby(df_all["date"].dt.date).size().rename("Total")
        by_date = by_date.merge(totals, left_on="Date", right_index=True)
        by_date["Share (%)"] = (100 * by_date["Flights"] / by_date["Total"]).round(1)
        by_date = _complete_daily_series(
            by_date,
            date_col="Date",
            value_cols=["Flights", "Total", "Share (%)"],
            start_date=ctx.start_date,
            end_date=ctx.end_date,
            group_cols=["Alliance"],
        )
        if not by_date.empty:
            fig = px.line(
                by_date,
                x="Date",
                y="Share (%)",
                color="Alliance",
            )
            fig.update_layout(height=350, yaxis=dict(title="Share (%)"))
            st.plotly_chart(fig, width="stretch")

    with tab_map:
        codes = sorted(df_cmp[ctx.airline_col].dropna().unique().tolist())
        top_codes = codes[: min(len(codes), ctx.top_n)]
        if ctx.global_mode:
            _render_network_map(
                df_cmp,
                ctx.airline_col,
                top_codes,
                ctx.geo_scope,
                top_routes_n=ctx.top_n,
            )
        else:
            map_by_country = False
            if ctx.show_country:
                map_point_by = st.radio(
                    "Map points by",
                    options=["City (airport)", "Country"],
                    index=1,
                    horizontal=True,
                    key="alliance_cmp_map_by",
                )
                map_by_country = map_point_by == "Country"
            _render_flight_map(
                df_cmp,
                ctx.direction,
                ctx.focus_airport,
                ctx.focus_lat,
                ctx.focus_lon,
                map_by_country,
                top_codes,
                ctx.airline_col,
                ctx.geo_scope,
                top_arcs_n=ctx.top_n,
            )
