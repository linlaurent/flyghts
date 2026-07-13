"""Single-airline deep dive tabs."""

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from flyghts.reference import get_airline, get_airport

from ...charts import _complete_daily_series, _start_flight_count_axis_at_zero
from ...components import _render_aggrid
from ...context import DashboardContext
from ...data import get_destination_column, map_point_label_to_aggregate
from ...formatting import _airport_province
from ...maps import _render_flight_map, _render_network_map
from ...tab_charts import (
    render_cargo_tab,
    render_primary_flights_over_time,
    render_scheduled_hour,
    render_secondary_grouped_over_time,
    render_weekday_average,
)


def render_single_airline_dive(
    ctx: DashboardContext,
    *,
    df_airline: pd.DataFrame,
    dive_icao: str,
) -> None:
    dive_name = get_airline(dive_icao).name if get_airline(dive_icao) else dive_icao
    st.subheader(f"{dive_name}")

    n_airline = len(df_airline)
    pct = 100 * n_airline / ctx.total_flights if ctx.total_flights > 0 else 0
    m1, m2 = st.columns(2)
    with m1:
        st.metric("Total flights", f"{n_airline:,}")
    with m2:
        st.metric("Share of traffic", f"{pct:.1f}%")

    dest_codes_airline = get_destination_column(
        df_airline, ctx.direction, ctx.focus_airport
    )
    dest_counts_airline = dest_codes_airline.value_counts()
    if ctx.global_mode:
        route_dest_airline = df_airline["destination"]
    elif ctx.direction == "Departures":
        route_dest_airline = df_airline["destination"]
    elif ctx.direction == "Arrivals":
        route_dest_airline = df_airline["origin"]
    else:
        route_dest_airline = pd.Series(
            np.where(
                df_airline["origin"] == ctx.focus_airport,
                df_airline["destination"],
                df_airline["origin"],
            ),
            index=df_airline.index,
        )

    _dive_tab_names = [
        "Top routes",
        "Flights over time",
        "Flights by hour",
        "Flights by weekday",
    ]
    if not ctx.is_us:
        _dive_tab_names.append("Cargo vs passenger")
    _dive_tab_names.append("Interactive map")
    _dive_tabs = st.tabs(_dive_tab_names)
    if ctx.is_us:
        tab_routes, tab_time, tab_hour, tab_weekday, tab_map = _dive_tabs
        tab_cargo = None
    else:
        (
            tab_routes,
            tab_time,
            tab_hour,
            tab_weekday,
            tab_cargo,
            tab_map,
        ) = _dive_tabs

    with tab_routes:
        if ctx.global_mode:
            # Show top O-D pairs for this airline
            od_counts_airline = (
                df_airline.groupby(["origin", "destination"])
                .size()
                .sort_values(ascending=False)
            )
            od_total_counts = ctx.df.groupby(["origin", "destination"]).size()
            od_n = min(ctx.top_n, len(od_counts_airline))
            od_rows: list[dict] = []
            for (orig, dest), cnt in od_counts_airline.head(od_n).items():
                o_info = get_airport(orig)
                d_info = get_airport(dest)
                o_lbl = f"{orig} ({o_info.city})" if o_info and o_info.city else orig
                d_lbl = f"{dest} ({d_info.city})" if d_info and d_info.city else dest
                total_on_od = od_total_counts.get((orig, dest), 0)
                share = 100 * cnt / total_on_od if total_on_od > 0 else 0
                od_rows.append(
                    {
                        "Route": f"{o_lbl} → {d_lbl}",
                        "Flights": cnt,
                        "Total on route": total_on_od,
                        "Share (%)": round(share, 1),
                    }
                )
            od_df = pd.DataFrame(
                od_rows,
                columns=[
                    "Route",
                    "Flights",
                    "Total on route",
                    "Share (%)",
                ],
            )
            if not od_df.empty:
                fig_od = px.bar(
                    od_df,
                    x="Flights",
                    y="Route",
                    orientation="h",
                    color="Share (%)",
                    color_continuous_scale="Viridis",
                    range_color=[0, 100],
                    labels={"Flights": "Number of flights"},
                    text=od_df["Share (%)"].apply(lambda x: f"{x}%"),
                    custom_data=[
                        "Flights",
                        "Total on route",
                        "Share (%)",
                    ],
                )
                fig_od.update_traces(
                    textposition="outside",
                    hovertemplate="%{y}<br>Flights: %{customdata[0]:,}<br>Total on route: %{customdata[1]:,}<br>Airline share: %{customdata[2]}%<extra></extra>",
                )
                fig_od.update_layout(
                    height=300 + od_n * 14,
                    yaxis={"categoryorder": "total ascending"},
                    showlegend=False,
                )
                _start_flight_count_axis_at_zero(fig_od, "x")
                st.plotly_chart(fig_od, width="stretch")
                _render_aggrid(od_df)
        else:
            route_n = min(ctx.top_n, len(dest_counts_airline))
            total_dest_counts = get_destination_column(
                ctx.df, ctx.direction, ctx.focus_airport
            ).value_counts()
            route_rows_d: list[dict] = []
            for iata, count in dest_counts_airline.head(route_n).items():
                info = get_airport(iata)
                total_to_dest = total_dest_counts.get(iata, 0)
                share = 100 * count / total_to_dest if total_to_dest > 0 else 0
                route_rows_d.append(
                    {
                        "Airport": iata,
                        "Name": info.name if info else "",
                        "City": info.city if info else "",
                        "Province": _airport_province(iata),
                        "Country": info.country if info else "",
                        "Flights": count,
                        "Total": total_to_dest,
                        "Share (%)": round(share, 1),
                    }
                )
            route_df = pd.DataFrame(
                route_rows_d,
                columns=[
                    "Airport",
                    "Name",
                    "City",
                    "Province",
                    "Country",
                    "Flights",
                    "Total",
                    "Share (%)",
                ],
            )
            if not route_df.empty:
                route_df["Label"] = route_df.apply(
                    lambda r: (
                        f"{r['Airport']} - {r['Name']}" if r["Name"] else r["Airport"]
                    ),
                    axis=1,
                )
                fig_route = px.bar(
                    route_df,
                    x="Flights",
                    y="Label",
                    orientation="h",
                    color="Share (%)",
                    color_continuous_scale="Viridis",
                    range_color=[0, 100],
                    labels={
                        "Flights": "Number of flights",
                        "Share (%)": "Share (%)",
                    },
                    text=route_df["Share (%)"].apply(lambda x: f"{x}%"),
                    custom_data=["Flights", "Total", "Share (%)"],
                )
                fig_route.update_traces(
                    textposition="outside",
                    hovertemplate="%{y}<br>Flights: %{customdata[0]:,}<br>Total: %{customdata[1]:,}<br>Share: %{customdata[2]}%<extra></extra>",
                )
                fig_route.update_layout(
                    height=300 + route_n * 12,
                    yaxis={"categoryorder": "total ascending"},
                    showlegend=False,
                )
                _start_flight_count_axis_at_zero(fig_route, "x")
                st.plotly_chart(fig_route, width="stretch")

                top_dests = set(dest_counts_airline.head(route_n).index)
                by_date_dest = (
                    df_airline.assign(route_dest=route_dest_airline)
                    .groupby([df_airline["date"].dt.date, "route_dest"])
                    .size()
                    .reset_index(name="Flights")
                )
                by_date_dest.columns = ["Date", "route_dest", "Flights"]
                by_date_dest = by_date_dest[by_date_dest["route_dest"].isin(top_dests)]
                if ctx.direction == "Departures":
                    dest_col_df = ctx.df["destination"]
                elif ctx.direction == "Arrivals":
                    dest_col_df = ctx.df["origin"]
                else:
                    dest_col_df = pd.Series(
                        np.where(
                            ctx.df["origin"] == ctx.focus_airport,
                            ctx.df["destination"],
                            ctx.df["origin"],
                        ),
                        index=ctx.df.index,
                    )
                total_by_date_dest = (
                    ctx.df.assign(route_dest=dest_col_df)
                    .groupby([ctx.df["date"].dt.date, "route_dest"])
                    .size()
                    .reset_index(name="Total")
                )
                total_by_date_dest.columns = [
                    "Date",
                    "route_dest",
                    "Total",
                ]
                by_date_dest = by_date_dest.merge(
                    total_by_date_dest,
                    on=["Date", "route_dest"],
                    how="left",
                )
                by_date_dest["Share (%)"] = (
                    100 * by_date_dest["Flights"] / by_date_dest["Total"]
                ).round(1)
                by_date_dest["Route"] = by_date_dest["route_dest"].apply(
                    lambda iata: get_airport(iata).name if get_airport(iata) else iata
                )
                by_date_dest = _complete_daily_series(
                    by_date_dest,
                    date_col="Date",
                    value_cols=["Flights", "Total", "Share (%)"],
                    start_date=ctx.start_date,
                    end_date=ctx.end_date,
                    group_cols=["route_dest", "Route"],
                )
                if not by_date_dest.empty:
                    fig_route_share_time = px.line(
                        by_date_dest,
                        x="Date",
                        y="Share (%)",
                        color="Route",
                        labels={"Share (%)": "Share (%)"},
                        custom_data=["Flights", "Total", "Route"],
                    )
                    fig_route_share_time.update_traces(
                        hovertemplate="%{customdata[2]}<br>%{x}<br>Flights: %{customdata[0]:,}<br>Total (denom): %{customdata[1]:,}<br>Share: %{y}%<extra></extra>",
                    )
                    fig_route_share_time.update_layout(
                        height=350,
                        title="Share of traffic (%) over time by route",
                        yaxis=dict(title="Share (%)"),
                    )
                    st.plotly_chart(fig_route_share_time, width="stretch")

                airline_flights_per_date = (
                    df_airline.groupby(df_airline["date"].dt.date)
                    .size()
                    .rename("AirlineTotal")
                )
                by_date_dest_norm = (
                    df_airline.assign(route_dest=route_dest_airline)
                    .groupby([df_airline["date"].dt.date, "route_dest"])
                    .size()
                    .reset_index(name="Flights")
                )
                by_date_dest_norm.columns = [
                    "Date",
                    "route_dest",
                    "Flights",
                ]
                by_date_dest_norm = by_date_dest_norm[
                    by_date_dest_norm["route_dest"].isin(top_dests)
                ]
                by_date_dest_norm = by_date_dest_norm.merge(
                    airline_flights_per_date,
                    left_on="Date",
                    right_index=True,
                    how="left",
                )
                by_date_dest_norm["Norm (%)"] = (
                    100
                    * by_date_dest_norm["Flights"]
                    / by_date_dest_norm["AirlineTotal"]
                ).round(1)
                by_date_dest_norm["Route"] = by_date_dest_norm["route_dest"].apply(
                    lambda iata: get_airport(iata).name if get_airport(iata) else iata
                )
                by_date_dest_norm = _complete_daily_series(
                    by_date_dest_norm,
                    date_col="Date",
                    value_cols=["Flights", "AirlineTotal", "Norm (%)"],
                    start_date=ctx.start_date,
                    end_date=ctx.end_date,
                    group_cols=["route_dest", "Route"],
                )
                if not by_date_dest_norm.empty:
                    fig_route_norm = px.line(
                        by_date_dest_norm,
                        x="Date",
                        y="Norm (%)",
                        color="Route",
                        labels={"Norm (%)": "Share of airline flights (%)"},
                        custom_data=[
                            "Flights",
                            "AirlineTotal",
                            "Route",
                        ],
                    )
                    fig_route_norm.update_traces(
                        hovertemplate="%{customdata[2]}<br>%{x}<br>Flights: %{customdata[0]:,}<br>Airline total (denom): %{customdata[1]:,}<br>Norm: %{y}%<extra></extra>",
                    )
                    fig_route_norm.update_layout(
                        height=350,
                        title="Share of airline flights (%) over time by route",
                        yaxis=dict(title="Share of airline flights (%)"),
                    )
                    st.plotly_chart(fig_route_norm, width="stretch")

            _render_aggrid(
                route_df[
                    [
                        "Airport",
                        "Name",
                        "City",
                        "Country",
                        "Flights",
                        "Share (%)",
                    ]
                ]
                if not route_df.empty
                else pd.DataFrame()
            )

    with tab_time:
        if render_primary_flights_over_time(df_airline, ctx):
            if not ctx.global_mode:
                total_by_date_dest = (
                    ctx.df.assign(route_dest=route_dest_airline)
                    .groupby([ctx.df["date"].dt.date, "route_dest"])
                    .size()
                    .reset_index(name="Total")
                    .rename(columns={"date": "Date"})
                )
                render_secondary_grouped_over_time(
                    df_airline,
                    ctx,
                    group_values=route_dest_airline,
                    top_groups=set(dest_counts_airline.head(ctx.top_n).index),
                    group_key_col="route_dest",
                    label_fn=lambda iata: (
                        get_airport(iata).name if get_airport(iata) else iata
                    ),
                    color_col="Route",
                    title="Flights over time by route",
                    totals=total_by_date_dest,
                    totals_merge="group",
                )

    with tab_hour:
        render_scheduled_hour(df_airline, ctx)

    with tab_weekday:
        render_weekday_average(df_airline)

    if tab_cargo is not None:
        with tab_cargo:
            render_cargo_tab(df_airline, ctx)

    with tab_map:
        if ctx.global_mode:
            _render_network_map(
                df_airline,
                ctx.airline_col,
                [dive_icao],
                ctx.geo_scope,
                top_routes_n=ctx.top_n,
            )
        else:
            map_point_opts = ["City (airport)", "Province"]
            if ctx.show_country:
                map_point_opts.append("Country")
            map_point_by_dive = st.radio(
                "Map points by",
                options=map_point_opts,
                index=len(map_point_opts) - 1 if ctx.show_country else 0,
                horizontal=True,
                help="Show each destination as a precise city/airport, or aggregate by province/state or country.",
                key="airline_dive_map_by",
            )
            _render_flight_map(
                df_airline,
                ctx.direction,
                ctx.focus_airport,
                ctx.focus_lat,
                ctx.focus_lon,
                map_point_label_to_aggregate(map_point_by_dive),
                [dive_icao],
                ctx.airline_col,
                ctx.geo_scope,
                use_traffic_colors=True,
                top_arcs_n=ctx.top_n,
            )
