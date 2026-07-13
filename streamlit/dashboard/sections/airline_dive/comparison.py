"""Airline comparison deep dive tabs."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import streamlit as st
from flyghts.reference import get_airline, get_airport

from ... import action_logger as al
from ...charts import _complete_daily_series, _start_flight_count_axis_at_zero
from ...components import _render_aggrid
from ...context import DashboardContext
from ...data import get_destination_column, map_point_label_to_aggregate
from ...maps import _render_flight_map, _render_network_map


def render_airline_comparison(
    ctx: DashboardContext,
    *,
    dive_airline_options: list[str],
    dive_display_to_code: dict[str, str],
) -> None:
    st.header("Airline comparison")
    if not dive_airline_options:
        st.info("No airlines in the filtered data.")
    else:
        sel_cmp_airlines = al.multiselect(
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
                df_a = ctx.df[ctx.df[ctx.airline_col] == code]
                n = len(df_a)
                share = 100 * n / ctx.total_flights if ctx.total_flights > 0 else 0
                n_dests = get_destination_column(
                    df_a, ctx.direction, ctx.focus_airport
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

            df_cmp = ctx.df[ctx.df[ctx.airline_col].isin(cmp_codes)].copy()
            df_cmp["Airline"] = df_cmp[ctx.airline_col].map(cmp_names)

            _cmp_tab_names = [
                "Top routes",
                "Flights over time",
                "Share of traffic over time",
                "Flights by hour",
            ]
            if not ctx.is_us:
                _cmp_tab_names.append("Cargo vs passenger")
            _cmp_tab_names.append("Interactive map")
            _cmp_tabs = st.tabs(_cmp_tab_names)
            if ctx.is_us:
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
                if ctx.global_mode:
                    all_top_ods: set[tuple[str, str]] = set()
                    for code in cmp_codes:
                        df_a = ctx.df[ctx.df[ctx.airline_col] == code]
                        top_ods = (
                            df_a.groupby(["origin", "destination"])
                            .size()
                            .sort_values(ascending=False)
                            .head(ctx.top_n)
                            .index
                        )
                        all_top_ods.update(top_ods)
                    cmp_od_rows: list[dict] = []
                    for code in cmp_codes:
                        df_a = ctx.df[ctx.df[ctx.airline_col] == code]
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
                        df_a = ctx.df[ctx.df[ctx.airline_col] == code]
                        top = (
                            get_destination_column(
                                df_a, ctx.direction, ctx.focus_airport
                            )
                            .value_counts()
                            .head(ctx.top_n)
                            .index
                        )
                        all_top_dests.update(top)

                    route_cmp_rows: list[dict] = []
                    for code in cmp_codes:
                        df_a = ctx.df[ctx.df[ctx.airline_col] == code]
                        dest_counts_a = get_destination_column(
                            df_a, ctx.direction, ctx.focus_airport
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
                    start_date=ctx.start_date,
                    end_date=ctx.end_date,
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
                    ctx.df.groupby(ctx.df["date"].dt.date).size().rename("Total")
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
                    start_date=ctx.start_date,
                    end_date=ctx.end_date,
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
                if not ctx.global_mode:
                    st.caption(
                        f"Departure time for flights from {ctx.focus_airport}; "
                        f"arrival time for flights to {ctx.focus_airport}."
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
                            df_a = ctx.df[ctx.df[ctx.airline_col] == code]
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
                            df_a = ctx.df[ctx.df[ctx.airline_col] == code]
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
                                    start_date=ctx.start_date,
                                    end_date=ctx.end_date,
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
                if ctx.global_mode:
                    _render_network_map(
                        df_cmp,
                        ctx.airline_col,
                        cmp_codes,
                        ctx.geo_scope,
                        top_routes_n=ctx.top_n,
                    )
                else:
                    map_point_opts = ["City (airport)", "Province"]
                    if ctx.show_country:
                        map_point_opts.append("Country")
                    map_point_by_cmp = al.radio(
                        "Map points by",
                        options=map_point_opts,
                        index=len(map_point_opts) - 1 if ctx.show_country else 0,
                        horizontal=True,
                        help="Show each destination as a precise city/airport, or aggregate by province/state or country.",
                        key="airline_cmp_map_by",
                    )
                    _render_flight_map(
                        df_cmp,
                        ctx.direction,
                        ctx.focus_airport,
                        ctx.focus_lat,
                        ctx.focus_lon,
                        map_point_label_to_aggregate(map_point_by_cmp),
                        cmp_codes,
                        ctx.airline_col,
                        ctx.geo_scope,
                        top_arcs_n=ctx.top_n,
                    )
