"""Single-alliance deep dive tabs."""

import pandas as pd
import plotly.express as px

import streamlit as st
from flyghts.reference import get_airport

from ... import action_logger as al
from ...charts import _start_flight_count_axis_at_zero
from ...components import _render_aggrid
from ...context import DashboardContext
from ...data import get_destination_column, map_point_label_to_aggregate
from ...formatting import _airline_label, _alliance_label
from ...maps import _render_flight_map, _render_network_map
from ...tab_charts import (
    render_cargo_tab,
    render_primary_flights_over_time,
    render_scheduled_hour,
    render_weekday_average,
)


def render_single_alliance_dive(
    ctx: DashboardContext,
    *,
    df_alliance: pd.DataFrame,
    alliance_id: str,
) -> None:
    label = _alliance_label(alliance_id)
    st.subheader(label)

    n = len(df_alliance)
    pct = 100 * n / ctx.total_flights if ctx.total_flights > 0 else 0
    member_count = df_alliance[ctx.airline_col].nunique()
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Total flights", f"{n:,}")
    with m2:
        st.metric("Share of traffic", f"{pct:.1f}%")
    with m3:
        st.metric("Member airlines in data", f"{member_count:,}")

    tab_names = [
        "Member airlines",
        "Top routes",
        "Flights over time",
        "Flights by hour",
        "Flights by weekday",
    ]
    if not ctx.is_us:
        tab_names.append("Cargo vs passenger")
    tab_names.append("Interactive map")
    tabs = st.tabs(tab_names)

    if ctx.is_us:
        tab_members, tab_routes, tab_time, tab_hour, tab_weekday, tab_map = tabs
        tab_cargo = None
    else:
        (
            tab_members,
            tab_routes,
            tab_time,
            tab_hour,
            tab_weekday,
            tab_cargo,
            tab_map,
        ) = tabs

    with tab_members:
        airline_counts = df_alliance[ctx.airline_col].value_counts()
        rows = []
        for icao, count in airline_counts.head(ctx.top_n).items():
            share = 100 * count / n if n > 0 else 0
            rows.append(
                {
                    "Airline": _airline_label(icao),
                    "ICAO": icao,
                    "Flights": int(count),
                    "Share (%)": round(share, 1),
                }
            )
        members_df = pd.DataFrame(
            rows, columns=["Airline", "ICAO", "Flights", "Share (%)"]
        )
        if not members_df.empty:
            fig = px.bar(
                members_df,
                x="Flights",
                y="Airline",
                orientation="h",
                color="Share (%)",
                color_continuous_scale="Teal",
                range_color=[0, 100],
                text=members_df["Share (%)"].apply(lambda x: f"{x}%"),
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(
                height=300 + len(members_df) * 14,
                yaxis={"categoryorder": "total ascending"},
                showlegend=False,
            )
            _start_flight_count_axis_at_zero(fig, "x")
            st.plotly_chart(fig, width="stretch")
            _render_aggrid(members_df)
            st.caption("Open Airline deep dive to explore a single member carrier.")
        else:
            st.caption("No member airlines in filtered data.")

    with tab_routes:
        if ctx.global_mode:
            od_counts = (
                df_alliance.groupby(["origin", "destination"])
                .size()
                .sort_values(ascending=False)
            )
            od_n = min(ctx.top_n, len(od_counts))
            od_rows = []
            for (orig, dest), cnt in od_counts.head(od_n).items():
                o_info = get_airport(orig)
                d_info = get_airport(dest)
                o_lbl = f"{orig} ({o_info.city})" if o_info and o_info.city else orig
                d_lbl = f"{dest} ({d_info.city})" if d_info and d_info.city else dest
                share = 100 * cnt / n if n > 0 else 0
                od_rows.append(
                    {
                        "Route": f"{o_lbl} → {d_lbl}",
                        "Flights": int(cnt),
                        "Share (%)": round(share, 1),
                    }
                )
            od_df = pd.DataFrame(od_rows)
            if not od_df.empty:
                fig_od = px.bar(
                    od_df,
                    x="Flights",
                    y="Route",
                    orientation="h",
                    color="Share (%)",
                    color_continuous_scale="Viridis",
                    range_color=[0, 100],
                    text=od_df["Share (%)"].apply(lambda x: f"{x}%"),
                )
                fig_od.update_traces(textposition="outside")
                fig_od.update_layout(
                    height=300 + od_n * 14,
                    yaxis={"categoryorder": "total ascending"},
                    showlegend=False,
                )
                _start_flight_count_axis_at_zero(fig_od, "x")
                st.plotly_chart(fig_od, width="stretch")
                _render_aggrid(od_df)
        else:
            dest_codes = get_destination_column(
                df_alliance, ctx.direction, ctx.focus_airport
            )
            dest_counts = dest_codes.value_counts()
            route_n = min(ctx.top_n, len(dest_counts))
            route_rows = []
            for iata, count in dest_counts.head(route_n).items():
                info = get_airport(iata)
                name = info.name if info else iata
                share = 100 * count / n if n > 0 else 0
                route_rows.append(
                    {
                        "Destination": f"{iata} - {name}" if name else iata,
                        "Flights": int(count),
                        "Share (%)": round(share, 1),
                    }
                )
            route_df = pd.DataFrame(route_rows)
            if not route_df.empty:
                fig_route = px.bar(
                    route_df,
                    x="Flights",
                    y="Destination",
                    orientation="h",
                    color="Share (%)",
                    color_continuous_scale="Viridis",
                    range_color=[0, 100],
                    text=route_df["Share (%)"].apply(lambda x: f"{x}%"),
                )
                fig_route.update_traces(textposition="outside")
                fig_route.update_layout(
                    height=300 + route_n * 12,
                    yaxis={"categoryorder": "total ascending"},
                    showlegend=False,
                )
                _start_flight_count_axis_at_zero(fig_route, "x")
                st.plotly_chart(fig_route, width="stretch")
                _render_aggrid(route_df)

    with tab_time:
        render_primary_flights_over_time(df_alliance, ctx)

    with tab_hour:
        render_scheduled_hour(df_alliance, ctx)

    with tab_weekday:
        render_weekday_average(df_alliance)

    if tab_cargo is not None:
        with tab_cargo:
            render_cargo_tab(df_alliance, ctx)

    with tab_map:
        map_codes = sorted(df_alliance[ctx.airline_col].dropna().unique().tolist())
        top_codes = map_codes[: min(len(map_codes), ctx.top_n)]
        if ctx.global_mode:
            _render_network_map(
                df_alliance,
                ctx.airline_col,
                top_codes,
                ctx.geo_scope,
                top_routes_n=ctx.top_n,
            )
        else:
            map_point_opts = ["City (airport)", "Province"]
            if ctx.show_country:
                map_point_opts.append("Country")
            map_point_by = al.radio(
                "Map points by",
                options=map_point_opts,
                index=len(map_point_opts) - 1 if ctx.show_country else 0,
                horizontal=True,
                key="alliance_dive_map_by",
            )
            _render_flight_map(
                df_alliance,
                ctx.direction,
                ctx.focus_airport,
                ctx.focus_lat,
                ctx.focus_lon,
                map_point_label_to_aggregate(map_point_by),
                top_codes,
                ctx.airline_col,
                ctx.geo_scope,
                use_traffic_colors=len(top_codes) <= 1,
                top_arcs_n=ctx.top_n,
            )
