"""Dashboard section: Airline deep dive."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from flyghts.reference import get_airline, get_airport

from ..context import DashboardContext

from ..charts import _complete_daily_series, _start_flight_count_axis_at_zero
from ..components import _render_aggrid
from ..data import get_destination_column
from ..maps import _render_flight_map, _render_network_map


def render_airline_dive(ctx: DashboardContext) -> None:
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

    st.header("Airline deep dive")
    dive_airlines = sorted(df[airline_col].dropna().unique().tolist())
    dive_airline_options: list[str] = []
    dive_display_to_code: dict[str, str] = {}
    for code in dive_airlines:
        display = (
            f"{code} - {info.name}"
            if (info := get_airline(code)) and info.name
            else code
        )
        dive_airline_options.append(display)
        dive_display_to_code[display] = code

    if not dive_airline_options:
        st.info("No airlines in the filtered data.")
    else:
        col_search_a, col_select_a = st.columns(2)
        with col_search_a:
            airline_search = st.text_input(
                "Search airlines by code or name",
                placeholder="e.g. CPA, Cathay, United",
                help="Filter the airline list by typing ICAO code or airline name.",
                key="airline_dive_search",
            )
        airline_search_lower = airline_search.strip().lower()
        if airline_search_lower:
            filtered_airlines = [
                a for a in dive_airline_options if airline_search_lower in a.lower()
            ]
        else:
            filtered_airlines = dive_airline_options

        if not filtered_airlines:
            st.info("No airlines match your search.")
        else:
            default_dive_idx = 0
            if not is_us:
                for i, opt in enumerate(filtered_airlines):
                    if (
                        opt.startswith("CPA -")
                        or dive_display_to_code.get(opt) == "CPA"
                    ):
                        default_dive_idx = i
                        break

            with col_select_a:
                sel_dive_airline = st.selectbox(
                    "Select airline",
                    options=filtered_airlines,
                    index=min(default_dive_idx, len(filtered_airlines) - 1),
                    help="Explore statistics for a single airline.",
                    key="airline_dive_select",
                )
            dive_icao = (
                dive_display_to_code.get(sel_dive_airline, "")
                if sel_dive_airline
                else ""
            )
            df_airline = (
                df[df[airline_col] == dive_icao] if dive_icao else pd.DataFrame()
            )

            if df_airline.empty:
                st.info("No flights for this airline in the selected filters.")
            else:
                dive_name = (
                    get_airline(dive_icao).name
                    if get_airline(dive_icao)
                    else dive_icao
                )
                st.subheader(f"{dive_name}")

                n_airline = len(df_airline)
                pct = 100 * n_airline / total_flights if total_flights > 0 else 0
                m1, m2 = st.columns(2)
                with m1:
                    st.metric("Total flights", f"{n_airline:,}")
                with m2:
                    st.metric("Share of traffic", f"{pct:.1f}%")

                dest_codes_airline = get_destination_column(
                    df_airline, direction, focus_airport
                )
                dest_counts_airline = dest_codes_airline.value_counts()
                if global_mode:
                    route_dest_airline = df_airline["destination"]
                elif direction == "Departures":
                    route_dest_airline = df_airline["destination"]
                elif direction == "Arrivals":
                    route_dest_airline = df_airline["origin"]
                else:
                    route_dest_airline = pd.Series(
                        np.where(
                            df_airline["origin"] == focus_airport,
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
                if not is_us:
                    _dive_tab_names.append("Cargo vs passenger")
                _dive_tab_names.append("Interactive map")
                _dive_tabs = st.tabs(_dive_tab_names)
                if is_us:
                    tab_routes, tab_time, tab_hour, tab_weekday, tab_map = (
                        _dive_tabs
                    )
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
                    if global_mode:
                        # Show top O-D pairs for this airline
                        od_counts_airline = (
                            df_airline.groupby(["origin", "destination"])
                            .size()
                            .sort_values(ascending=False)
                        )
                        od_total_counts = df.groupby(
                            ["origin", "destination"]
                        ).size()
                        od_n = min(top_n, len(od_counts_airline))
                        od_rows: list[dict] = []
                        for (orig, dest), cnt in od_counts_airline.head(
                            od_n
                        ).items():
                            o_info = get_airport(orig)
                            d_info = get_airport(dest)
                            o_lbl = (
                                f"{orig} ({o_info.city})"
                                if o_info and o_info.city
                                else orig
                            )
                            d_lbl = (
                                f"{dest} ({d_info.city})"
                                if d_info and d_info.city
                                else dest
                            )
                            total_on_od = od_total_counts.get((orig, dest), 0)
                            share = (
                                100 * cnt / total_on_od if total_on_od > 0 else 0
                            )
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
                        route_n = min(top_n, len(dest_counts_airline))
                        total_dest_counts = get_destination_column(
                            df, direction, focus_airport
                        ).value_counts()
                        route_rows_d: list[dict] = []
                        for iata, count in dest_counts_airline.head(
                            route_n
                        ).items():
                            info = get_airport(iata)
                            total_to_dest = total_dest_counts.get(iata, 0)
                            share = (
                                100 * count / total_to_dest
                                if total_to_dest > 0
                                else 0
                            )
                            route_rows_d.append(
                                {
                                    "Airport": iata,
                                    "Name": info.name if info else "",
                                    "City": info.city if info else "",
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
                                "Country",
                                "Flights",
                                "Total",
                                "Share (%)",
                            ],
                        )
                        if not route_df.empty:
                            route_df["Label"] = route_df.apply(
                                lambda r: (
                                    f"{r['Airport']} - {r['Name']}"
                                    if r["Name"]
                                    else r["Airport"]
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
                            by_date_dest = by_date_dest[
                                by_date_dest["route_dest"].isin(top_dests)
                            ]
                            if direction == "Departures":
                                dest_col_df = df["destination"]
                            elif direction == "Arrivals":
                                dest_col_df = df["origin"]
                            else:
                                dest_col_df = pd.Series(
                                    np.where(
                                        df["origin"] == focus_airport,
                                        df["destination"],
                                        df["origin"],
                                    ),
                                    index=df.index,
                                )
                            total_by_date_dest = (
                                df.assign(route_dest=dest_col_df)
                                .groupby([df["date"].dt.date, "route_dest"])
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
                                100
                                * by_date_dest["Flights"]
                                / by_date_dest["Total"]
                            ).round(1)
                            by_date_dest["Route"] = by_date_dest[
                                "route_dest"
                            ].apply(
                                lambda iata: (
                                    get_airport(iata).name
                                    if get_airport(iata)
                                    else iata
                                )
                            )
                            by_date_dest = _complete_daily_series(
                                by_date_dest,
                                date_col="Date",
                                value_cols=["Flights", "Total", "Share (%)"],
                                start_date=start_date,
                                end_date=end_date,
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
                                st.plotly_chart(
                                    fig_route_share_time, width="stretch"
                                )

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
                            by_date_dest_norm["Route"] = by_date_dest_norm[
                                "route_dest"
                            ].apply(
                                lambda iata: (
                                    get_airport(iata).name
                                    if get_airport(iata)
                                    else iata
                                )
                            )
                            by_date_dest_norm = _complete_daily_series(
                                by_date_dest_norm,
                                date_col="Date",
                                value_cols=["Flights", "AirlineTotal", "Norm (%)"],
                                start_date=start_date,
                                end_date=end_date,
                                group_cols=["route_dest", "Route"],
                            )
                            if not by_date_dest_norm.empty:
                                fig_route_norm = px.line(
                                    by_date_dest_norm,
                                    x="Date",
                                    y="Norm (%)",
                                    color="Route",
                                    labels={
                                        "Norm (%)": "Share of airline flights (%)"
                                    },
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
                                    yaxis=dict(
                                        title="Share of airline flights (%)"
                                    ),
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
                    by_date = (
                        df_airline.groupby(df_airline["date"].dt.date)
                        .size()
                        .reset_index(name="Flights")
                    )
                    by_date.columns = ["Date", "Flights"]
                    if not by_date.empty:
                        total_by_date = (
                            df.groupby(df["date"].dt.date)
                            .size()
                            .reset_index(name="Total")
                        )
                        total_by_date.columns = ["Date", "Total"]
                        share_df = by_date.merge(
                            total_by_date, on="Date", how="left"
                        )
                        share_df["Share"] = (
                            100 * share_df["Flights"] / share_df["Total"]
                        ).fillna(0)
                        share_df = _complete_daily_series(
                            share_df,
                            date_col="Date",
                            value_cols=["Flights", "Total", "Share"],
                            start_date=start_date,
                            end_date=end_date,
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

                        if not global_mode:
                            top_dests_time = set(
                                dest_counts_airline.head(top_n).index
                            )
                            by_date_dest_time = (
                                df_airline.assign(route_dest=route_dest_airline)
                                .groupby([df_airline["date"].dt.date, "route_dest"])
                                .size()
                                .reset_index(name="Flights")
                            )
                            by_date_dest_time.columns = [
                                "Date",
                                "route_dest",
                                "Flights",
                            ]
                            by_date_dest_time = by_date_dest_time[
                                by_date_dest_time["route_dest"].isin(top_dests_time)
                            ]
                            by_date_dest_time = by_date_dest_time.merge(
                                total_by_date_dest[["Date", "route_dest", "Total"]],
                                on=["Date", "route_dest"],
                                how="left",
                            )
                            by_date_dest_time["Route"] = by_date_dest_time[
                                "route_dest"
                            ].apply(
                                lambda iata: (
                                    get_airport(iata).name
                                    if get_airport(iata)
                                    else iata
                                )
                            )
                            by_date_dest_time = _complete_daily_series(
                                by_date_dest_time,
                                date_col="Date",
                                value_cols=["Flights", "Total"],
                                start_date=start_date,
                                end_date=end_date,
                                group_cols=["route_dest", "Route"],
                            )
                            if not by_date_dest_time.empty:
                                fig_route_count_time = px.line(
                                    by_date_dest_time,
                                    x="Date",
                                    y="Flights",
                                    color="Route",
                                    labels={"Flights": "Number of flights"},
                                    custom_data=["Total", "Route"],
                                )
                                fig_route_count_time.update_traces(
                                    hovertemplate="%{customdata[1]}<br>%{x}<br>Flights: %{y:,}<br>Total (denom): %{customdata[0]:,}<extra></extra>",
                                )
                                fig_route_count_time.update_layout(
                                    height=350,
                                    title="Flights over time by route",
                                )
                                _start_flight_count_axis_at_zero(
                                    fig_route_count_time, "y"
                                )
                                st.plotly_chart(
                                    fig_route_count_time, width="stretch"
                                )
                    else:
                        st.caption("No date data.")

                with tab_hour:
                    if not global_mode:
                        st.caption(
                            f"Departure time for flights from {focus_airport}; "
                            f"arrival time for flights to {focus_airport}."
                        )
                    if "scheduled_time" in df_airline.columns:
                        df_airline_hour = df_airline.dropna(
                            subset=["scheduled_time"]
                        )
                        df_airline_hour = df_airline_hour.copy()
                        df_airline_hour["hour"] = pd.to_datetime(
                            df_airline_hour["scheduled_time"], errors="coerce"
                        ).dt.hour
                        df_airline_hour = df_airline_hour.dropna(subset=["hour"])
                        by_hour = (
                            df_airline_hour.groupby("hour")
                            .size()
                            .reset_index(name="Flights")
                        )
                        if not by_hour.empty:
                            fig_hour = px.bar(
                                by_hour,
                                x="hour",
                                y="Flights",
                                labels={
                                    "hour": "Hour of day",
                                    "Flights": "Number of flights",
                                },
                            )
                            fig_hour.update_layout(height=350)
                            _start_flight_count_axis_at_zero(fig_hour, "y")
                            st.plotly_chart(fig_hour, width="stretch")
                        else:
                            st.caption("No scheduled time data for this airline.")
                    else:
                        st.caption("No scheduled_time column in data.")

                with tab_weekday:
                    _weekday_order = [
                        "Monday",
                        "Tuesday",
                        "Wednesday",
                        "Thursday",
                        "Friday",
                        "Saturday",
                        "Sunday",
                    ]
                    _wd = df_airline.copy()
                    _wd["weekday"] = _wd["date"].dt.day_name()
                    _wd_total = _wd.groupby("weekday").size().rename("Total")
                    _wd_dates = (
                        _wd.groupby("weekday")["date"]
                        .apply(lambda s: s.dt.date.nunique())
                        .rename("Days")
                    )
                    _wd_df = pd.concat([_wd_total, _wd_dates], axis=1).reset_index()
                    _wd_df["Avg"] = (_wd_df["Total"] / _wd_df["Days"]).round(1)
                    _wd_df["weekday"] = pd.Categorical(
                        _wd_df["weekday"], categories=_weekday_order, ordered=True
                    )
                    _wd_df = _wd_df.sort_values("weekday")
                    if not _wd_df.empty:
                        fig_wd = px.bar(
                            _wd_df,
                            x="weekday",
                            y="Avg",
                            labels={
                                "weekday": "Day of week",
                                "Avg": "Avg flights per day",
                            },
                            custom_data=["Total", "Days"],
                        )
                        fig_wd.update_traces(
                            hovertemplate="%{x}<br>Avg: %{y}<br>Total: %{customdata[0]:,}<br>Days: %{customdata[1]}<extra></extra>",
                        )
                        fig_wd.update_layout(height=350)
                        _start_flight_count_axis_at_zero(fig_wd, "y")
                        st.plotly_chart(fig_wd, width="stretch")
                    else:
                        st.caption("No date data for weekday analysis.")

                if tab_cargo is not None:
                    with tab_cargo:
                        if "cargo" in df_airline.columns:
                            cargo_by_date = (
                                df_airline.groupby(
                                    [df_airline["date"].dt.date, "cargo"]
                                )
                                .size()
                                .reset_index(name="Flights")
                            )
                            cargo_by_date["Type"] = cargo_by_date["cargo"].map(
                                {True: "Cargo", False: "Passenger"}
                            )
                            cargo_by_date = _complete_daily_series(
                                cargo_by_date,
                                date_col="date",
                                value_cols=["Flights"],
                                start_date=start_date,
                                end_date=end_date,
                                group_cols=["cargo", "Type"],
                            )
                            if not cargo_by_date.empty:
                                fig_cargo = px.line(
                                    cargo_by_date,
                                    x="date",
                                    y="Flights",
                                    color="Type",
                                    labels={
                                        "date": "Date",
                                        "Flights": "Number of flights",
                                    },
                                    custom_data=["Type"],
                                )
                                fig_cargo.update_traces(
                                    hovertemplate="%{customdata[0]}<br>%{x}<br>Flights: %{y:,}<extra></extra>",
                                )
                                fig_cargo.update_layout(height=350)
                                _start_flight_count_axis_at_zero(fig_cargo, "y")
                                st.plotly_chart(fig_cargo, width="stretch")
                            cargo_passenger = (df_airline["cargo"] == False).sum()
                            cargo_cargo = (df_airline["cargo"] == True).sum()
                            cargo_df = pd.DataFrame(
                                [
                                    {
                                        "Type": "Passenger",
                                        "Flights": cargo_passenger,
                                    },
                                    {"Type": "Cargo", "Flights": cargo_cargo},
                                ]
                            )
                            _render_aggrid(cargo_df)
                        else:
                            st.caption("No cargo column in data.")

                with tab_map:
                    if global_mode:
                        _render_network_map(
                            df_airline,
                            airline_col,
                            [dive_icao],
                            geo_scope,
                            top_routes_n=top_n,
                        )
                    else:
                        if show_country:
                            map_point_by_dive = st.radio(
                                "Map points by",
                                options=["City (airport)", "Country"],
                                index=1,
                                horizontal=True,
                                help="Show each destination as a precise city/airport, or aggregate by country.",
                                key="airline_dive_map_by",
                            )
                        else:
                            map_point_by_dive = "City (airport)"
                        map_by_country_dive = map_point_by_dive == "Country"
                        _render_flight_map(
                            df_airline,
                            direction,
                            focus_airport,
                            focus_lat,
                            focus_lon,
                            map_by_country_dive,
                            [dive_icao],
                            airline_col,
                            geo_scope,
                            use_traffic_colors=True,
                            top_arcs_n=top_n,
                        )

    # ── Airline comparison ──
    st.header("Airline comparison")
    if not dive_airline_options:
        st.info("No airlines in the filtered data.")
    else:
        sel_cmp_airlines = st.multiselect(
            "Select airlines to compare",
            options=dive_airline_options,
            default=[],
            help="Pick 2 or more airlines to compare side by side.",
            key="airline_cmp_select",
        )
        cmp_codes = [dive_display_to_code.get(d, "") for d in sel_cmp_airlines]
        cmp_codes = [c for c in cmp_codes if c]

        if len(cmp_codes) < 2:
            st.info("Select at least 2 airlines to compare.")
        else:
            cmp_names: dict[str, str] = {}
            for code in cmp_codes:
                a_info = get_airline(code)
                cmp_names[code] = a_info.name if a_info else code

            summary_rows = []
            for code in cmp_codes:
                df_a = df[df[airline_col] == code]
                n = len(df_a)
                share = 100 * n / total_flights if total_flights > 0 else 0
                n_dests = get_destination_column(
                    df_a, direction, focus_airport
                ).nunique()
                pax = int((~df_a["cargo"]).sum()) if "cargo" in df_a.columns else n
                cargo_n = int(df_a["cargo"].sum()) if "cargo" in df_a.columns else 0
                summary_rows.append(
                    {
                        "Airline": cmp_names[code],
                        "ICAO": code,
                        "Flights": n,
                        "Share (%)": round(share, 1),
                        "Destinations": n_dests,
                        "Passenger": pax,
                        "Cargo": cargo_n,
                    }
                )
            summary_cmp_df = pd.DataFrame(summary_rows)
            _render_aggrid(summary_cmp_df)

            df_cmp = df[df[airline_col].isin(cmp_codes)].copy()
            df_cmp["Airline"] = df_cmp[airline_col].map(cmp_names)

            _cmp_tab_names = [
                "Top routes",
                "Flights over time",
                "Share of traffic over time",
                "Flights by hour",
            ]
            if not is_us:
                _cmp_tab_names.append("Cargo vs passenger")
            _cmp_tab_names.append("Interactive map")
            _cmp_tabs = st.tabs(_cmp_tab_names)
            if is_us:
                (
                    tab_cmp_routes,
                    tab_cmp_time,
                    tab_cmp_share,
                    tab_cmp_hour,
                    tab_cmp_map,
                ) = _cmp_tabs
                tab_cmp_cargo = None
            else:
                (
                    tab_cmp_routes,
                    tab_cmp_time,
                    tab_cmp_share,
                    tab_cmp_hour,
                    tab_cmp_cargo,
                    tab_cmp_map,
                ) = _cmp_tabs

            with tab_cmp_routes:
                if global_mode:
                    all_top_ods: set[tuple[str, str]] = set()
                    for code in cmp_codes:
                        df_a = df[df[airline_col] == code]
                        top_ods = (
                            df_a.groupby(["origin", "destination"])
                            .size()
                            .sort_values(ascending=False)
                            .head(top_n)
                            .index
                        )
                        all_top_ods.update(top_ods)
                    cmp_od_rows: list[dict] = []
                    for code in cmp_codes:
                        df_a = df[df[airline_col] == code]
                        od_counts_a = df_a.groupby(["origin", "destination"]).size()
                        for orig, dest in sorted(all_top_ods):
                            cnt = od_counts_a.get((orig, dest), 0)
                            o_info = get_airport(orig)
                            d_info = get_airport(dest)
                            o_lbl = (
                                f"{orig} ({o_info.city})"
                                if o_info and o_info.city
                                else orig
                            )
                            d_lbl = (
                                f"{dest} ({d_info.city})"
                                if d_info and d_info.city
                                else dest
                            )
                            cmp_od_rows.append(
                                {
                                    "Route": f"{o_lbl}→{d_lbl}",
                                    "Airline": cmp_names[code],
                                    "Flights": cnt,
                                }
                            )
                    cmp_od_df = pd.DataFrame(cmp_od_rows)
                    if not cmp_od_df.empty:
                        fig_cmp_routes = px.bar(
                            cmp_od_df,
                            x="Flights",
                            y="Route",
                            color="Airline",
                            orientation="h",
                            barmode="group",
                            labels={"Flights": "Number of flights"},
                        )
                        fig_cmp_routes.update_layout(
                            height=400 + len(all_top_ods) * 25,
                            yaxis={"categoryorder": "total ascending"},
                        )
                        _start_flight_count_axis_at_zero(fig_cmp_routes, "x")
                        st.plotly_chart(fig_cmp_routes, width="stretch")
                else:
                    all_top_dests: set[str] = set()
                    for code in cmp_codes:
                        df_a = df[df[airline_col] == code]
                        top = (
                            get_destination_column(df_a, direction, focus_airport)
                            .value_counts()
                            .head(top_n)
                            .index
                        )
                        all_top_dests.update(top)

                    route_cmp_rows: list[dict] = []
                    for code in cmp_codes:
                        df_a = df[df[airline_col] == code]
                        dest_counts_a = get_destination_column(
                            df_a, direction, focus_airport
                        ).value_counts()
                        for iata in sorted(all_top_dests):
                            count = dest_counts_a.get(iata, 0)
                            apt_info = get_airport(iata)
                            label = (
                                f"{iata} - {apt_info.name}"
                                if apt_info and apt_info.name
                                else iata
                            )
                            route_cmp_rows.append(
                                {
                                    "Destination": label,
                                    "Airline": cmp_names[code],
                                    "Flights": count,
                                }
                            )
                    route_cmp_df = pd.DataFrame(route_cmp_rows)
                    if not route_cmp_df.empty:
                        fig_cmp_routes = px.bar(
                            route_cmp_df,
                            x="Flights",
                            y="Destination",
                            color="Airline",
                            orientation="h",
                            barmode="group",
                            labels={"Flights": "Number of flights"},
                        )
                        fig_cmp_routes.update_layout(
                            height=400 + len(all_top_dests) * 25,
                            yaxis={"categoryorder": "total ascending"},
                        )
                        _start_flight_count_axis_at_zero(fig_cmp_routes, "x")
                        st.plotly_chart(fig_cmp_routes, width="stretch")

            with tab_cmp_time:
                by_date_cmp = (
                    df_cmp.groupby([df_cmp["date"].dt.date, "Airline"])
                    .size()
                    .reset_index(name="Flights")
                )
                by_date_cmp.columns = ["Date", "Airline", "Flights"]
                by_date_cmp = _complete_daily_series(
                    by_date_cmp,
                    date_col="Date",
                    value_cols=["Flights"],
                    start_date=start_date,
                    end_date=end_date,
                    group_cols=["Airline"],
                )
                if not by_date_cmp.empty:
                    fig_cmp_time = px.line(
                        by_date_cmp,
                        x="Date",
                        y="Flights",
                        color="Airline",
                        labels={"Flights": "Number of flights"},
                    )
                    fig_cmp_time.update_layout(height=400)
                    _start_flight_count_axis_at_zero(fig_cmp_time, "y")
                    st.plotly_chart(fig_cmp_time, width="stretch")
                else:
                    st.caption("No date data.")

            with tab_cmp_share:
                total_by_date_cmp = (
                    df.groupby(df["date"].dt.date).size().rename("Total")
                )
                share_cmp = (
                    df_cmp.groupby([df_cmp["date"].dt.date, "Airline"])
                    .size()
                    .reset_index(name="Flights")
                )
                share_cmp.columns = ["Date", "Airline", "Flights"]
                share_cmp = share_cmp.merge(
                    total_by_date_cmp, left_on="Date", right_index=True, how="left"
                )
                share_cmp["Share (%)"] = (
                    100 * share_cmp["Flights"] / share_cmp["Total"]
                ).round(1)
                share_cmp = _complete_daily_series(
                    share_cmp,
                    date_col="Date",
                    value_cols=["Flights", "Total", "Share (%)"],
                    start_date=start_date,
                    end_date=end_date,
                    group_cols=["Airline"],
                )
                if not share_cmp.empty:
                    fig_cmp_share = px.line(
                        share_cmp,
                        x="Date",
                        y="Share (%)",
                        color="Airline",
                        labels={"Share (%)": "Share of traffic (%)"},
                        custom_data=["Flights", "Total"],
                    )
                    fig_cmp_share.update_traces(
                        hovertemplate="%{data.name}<br>%{x}<br>Flights: %{customdata[0]:,}<br>Total: %{customdata[1]:,}<br>Share: %{y}%<extra></extra>",
                    )
                    fig_cmp_share.update_layout(height=400)
                    st.plotly_chart(fig_cmp_share, width="stretch")
                else:
                    st.caption("No date data.")

            with tab_cmp_hour:
                if not global_mode:
                    st.caption(
                        f"Departure time for flights from {focus_airport}; "
                        f"arrival time for flights to {focus_airport}."
                    )
                if "scheduled_time" in df_cmp.columns:
                    df_cmp_hour = df_cmp.dropna(subset=["scheduled_time"]).copy()
                    df_cmp_hour["hour"] = pd.to_datetime(
                        df_cmp_hour["scheduled_time"], errors="coerce"
                    ).dt.hour
                    df_cmp_hour = df_cmp_hour.dropna(subset=["hour"])
                    by_hour_cmp = (
                        df_cmp_hour.groupby(["hour", "Airline"])
                        .size()
                        .reset_index(name="Flights")
                    )
                    if not by_hour_cmp.empty:
                        fig_cmp_hour = px.bar(
                            by_hour_cmp,
                            x="hour",
                            y="Flights",
                            color="Airline",
                            barmode="group",
                            labels={
                                "hour": "Hour of day",
                                "Flights": "Number of flights",
                            },
                        )
                        fig_cmp_hour.update_layout(height=400)
                        _start_flight_count_axis_at_zero(fig_cmp_hour, "y")
                        st.plotly_chart(fig_cmp_hour, width="stretch")
                    else:
                        st.caption("No scheduled time data.")
                else:
                    st.caption("No scheduled_time column in data.")

            if tab_cmp_cargo is not None:
                with tab_cmp_cargo:
                    if "cargo" in df_cmp.columns:
                        cargo_cmp_rows = []
                        for code in cmp_codes:
                            df_a = df[df[airline_col] == code]
                            pax = (
                                int((~df_a["cargo"]).sum())
                                if "cargo" in df_a.columns
                                else 0
                            )
                            cargo_n = (
                                int(df_a["cargo"].sum())
                                if "cargo" in df_a.columns
                                else 0
                            )
                            cargo_cmp_rows.append(
                                {
                                    "Airline": cmp_names[code],
                                    "Type": "Passenger",
                                    "Flights": pax,
                                }
                            )
                            cargo_cmp_rows.append(
                                {
                                    "Airline": cmp_names[code],
                                    "Type": "Cargo",
                                    "Flights": cargo_n,
                                }
                            )
                        cargo_cmp_df = pd.DataFrame(cargo_cmp_rows)
                        if not cargo_cmp_df.empty:
                            fig_cmp_cargo = px.bar(
                                cargo_cmp_df,
                                x="Flights",
                                y="Airline",
                                color="Type",
                                orientation="h",
                                barmode="group",
                                labels={"Flights": "Number of flights"},
                            )
                            fig_cmp_cargo.update_layout(
                                height=200 + len(cmp_codes) * 60
                            )
                            _start_flight_count_axis_at_zero(fig_cmp_cargo, "x")
                            st.plotly_chart(fig_cmp_cargo, width="stretch")

                        cargo_time_parts = []
                        for code in cmp_codes:
                            df_a = df[df[airline_col] == code]
                            if "cargo" in df_a.columns:
                                by_dt_cargo = (
                                    df_a.groupby([df_a["date"].dt.date, "cargo"])
                                    .size()
                                    .reset_index(name="Flights")
                                )
                                by_dt_cargo["Type"] = by_dt_cargo["cargo"].map(
                                    {True: "Cargo", False: "Passenger"}
                                )
                                by_dt_cargo["Label"] = (
                                    cmp_names[code] + " - " + by_dt_cargo["Type"]
                                )
                                cargo_time_parts.append(by_dt_cargo)
                        if cargo_time_parts:
                            cargo_time_df = pd.concat(
                                cargo_time_parts, ignore_index=True
                            )
                            if not cargo_time_df.empty:
                                cargo_time_df = _complete_daily_series(
                                    cargo_time_df,
                                    date_col="date",
                                    value_cols=["Flights"],
                                    start_date=start_date,
                                    end_date=end_date,
                                    group_cols=["cargo", "Type", "Label"],
                                )
                                fig_cmp_cargo_time = px.line(
                                    cargo_time_df,
                                    x="date",
                                    y="Flights",
                                    color="Label",
                                    labels={
                                        "date": "Date",
                                        "Flights": "Number of flights",
                                    },
                                )
                                fig_cmp_cargo_time.update_layout(height=400)
                                _start_flight_count_axis_at_zero(
                                    fig_cmp_cargo_time, "y"
                                )
                                st.plotly_chart(fig_cmp_cargo_time, width="stretch")
                    else:
                        st.caption("No cargo column in data.")

            with tab_cmp_map:
                if global_mode:
                    _render_network_map(
                        df_cmp,
                        airline_col,
                        cmp_codes,
                        geo_scope,
                        top_routes_n=top_n,
                    )
                else:
                    if show_country:
                        map_point_by_cmp = st.radio(
                            "Map points by",
                            options=["City (airport)", "Country"],
                            index=1,
                            horizontal=True,
                            help="Show each destination as a precise city/airport, or aggregate by country.",
                            key="airline_cmp_map_by",
                        )
                    else:
                        map_point_by_cmp = "City (airport)"
                    map_by_country_cmp = map_point_by_cmp == "Country"
                    _render_flight_map(
                        df_cmp,
                        direction,
                        focus_airport,
                        focus_lat,
                        focus_lon,
                        map_by_country_cmp,
                        cmp_codes,
                        airline_col,
                        geo_scope,
                        top_arcs_n=top_n,
                    )
