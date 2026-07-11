"""Dashboard section: Overview."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from flyghts.reference import get_airline, get_airport

from ..context import DashboardContext

from ..charts import _render_overview_flights_per_day, _start_flight_count_axis_at_zero
from ..components import _render_aggrid
from ..data import get_destination_column
from ..maps import _render_flight_map, _render_network_map


def render_overview(ctx: DashboardContext) -> None:
    chart_h = 320
    airline_counts = ctx.df[ctx.airline_col].value_counts()
    top_airlines = airline_counts.head(ctx.top_n)
    airline_rows = []
    for icao, count in top_airlines.items():
        info = get_airline(icao)
        share = 100 * count / ctx.total_flights if ctx.total_flights > 0 else 0
        airline_rows.append(
            {
                "Airline": info.name if info else icao,
                "Flights": count,
                "Share (%)": round(share, 1),
            }
        )
    airline_df = pd.DataFrame(
        airline_rows, columns=["Airline", "Flights", "Share (%)"]
    )
    fig_airlines = px.bar(
        airline_df,
        x="Flights",
        y="Airline",
        orientation="h",
        color="Flights",
        color_continuous_scale="Blues",
        text=airline_df["Share (%)"].apply(lambda x: f"{x}%"),
    )
    fig_airlines.update_traces(textposition="outside")
    fig_airlines.update_layout(
        height=chart_h, yaxis={"categoryorder": "total ascending"}, showlegend=False
    )
    _start_flight_count_axis_at_zero(fig_airlines, "x")

    if ctx.global_mode:
        # ── Global mode: top routes + top airports ──
        route_counts_all = (
            ctx.df.groupby(["origin", "destination"])
            .size()
            .sort_values(ascending=False)
        )
        route_rows: list[dict] = []
        for (orig, dest), cnt in route_counts_all.head(ctx.top_n).items():
            o_info = get_airport(orig)
            d_info = get_airport(dest)
            o_label = f"{orig} ({o_info.city})" if o_info and o_info.city else orig
            d_label = f"{dest} ({d_info.city})" if d_info and d_info.city else dest
            share = 100 * cnt / ctx.total_flights if ctx.total_flights > 0 else 0
            route_rows.append(
                {
                    "Route": f"{o_label} → {d_label}",
                    "Flights": cnt,
                    "Share (%)": round(share, 1),
                }
            )
        route_overview_df = pd.DataFrame(
            route_rows, columns=["Route", "Flights", "Share (%)"]
        )

        apt_traffic = (
            pd.concat(
                [
                    ctx.df["origin"].value_counts(),
                    ctx.df["destination"].value_counts(),
                ]
            )
            .groupby(level=0)
            .sum()
            .sort_values(ascending=False)
        )
        apt_rows: list[dict] = []
        for iata, cnt in apt_traffic.head(ctx.top_n).items():
            info = get_airport(iata)
            share = 100 * cnt / ctx.total_flights if ctx.total_flights > 0 else 0
            label = f"{iata} - {info.name}" if info and info.name else iata
            apt_rows.append(
                {"Label": label, "Flights": cnt, "Share (%)": round(share, 1)}
            )
        apt_overview_df = pd.DataFrame(
            apt_rows, columns=["Label", "Flights", "Share (%)"]
        )

        city_counts_g: dict[str, int] = {}
        for iata, cnt in apt_traffic.items():
            info = get_airport(iata)
            city = info.city if info and info.city else iata
            city_counts_g[city] = city_counts_g.get(city, 0) + cnt
        city_sorted_g = sorted(city_counts_g.items(), key=lambda x: -x[1])[:ctx.top_n]
        city_df_g = pd.DataFrame(
            [{"City": c, "Flights": n} for c, n in city_sorted_g],
            columns=["City", "Flights"],
        )
        city_df_g["Share (%)"] = (
            (100 * city_df_g["Flights"] / ctx.total_flights).round(1)
            if ctx.total_flights
            else 0.0
        )

        fig_routes_ov = px.bar(
            route_overview_df,
            x="Flights",
            y="Route",
            orientation="h",
            color="Flights",
            color_continuous_scale="Greens",
            text=route_overview_df["Share (%)"].apply(lambda x: f"{x}%"),
        )
        fig_routes_ov.update_traces(textposition="outside")
        fig_routes_ov.update_layout(
            height=chart_h + 80,
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
        )
        _start_flight_count_axis_at_zero(fig_routes_ov, "x")

        fig_apt_ov = px.bar(
            apt_overview_df,
            x="Flights",
            y="Label",
            orientation="h",
            color="Flights",
            color_continuous_scale="Oranges",
            text=apt_overview_df["Share (%)"].apply(lambda x: f"{x}%"),
        )
        fig_apt_ov.update_traces(textposition="outside")
        fig_apt_ov.update_layout(
            height=chart_h,
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
        )
        _start_flight_count_axis_at_zero(fig_apt_ov, "x")

        fig_city_g = px.bar(
            city_df_g,
            x="Flights",
            y="City",
            orientation="h",
            color="Flights",
            color_continuous_scale="Purples",
            text=city_df_g["Share (%)"].apply(lambda x: f"{x}%"),
        )
        fig_city_g.update_traces(textposition="outside")
        fig_city_g.update_layout(
            height=chart_h,
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
        )
        _start_flight_count_axis_at_zero(fig_city_g, "x")

        r1c1, r1c2 = st.columns(2)
        with r1c1:
            st.subheader("Top airlines by flight count")
            st.plotly_chart(fig_airlines, width="stretch")
        with r1c2:
            st.subheader("Top airports by total traffic")
            st.plotly_chart(fig_apt_ov, width="stretch")

        r2c1, r2c2 = st.columns(2)
        with r2c1:
            st.subheader("Top routes (O-D pairs)")
            st.plotly_chart(fig_routes_ov, width="stretch")
        with r2c2:
            st.subheader("Top cities by total traffic")
            st.plotly_chart(fig_city_g, width="stretch")

        _render_overview_flights_per_day(
            ctx.df,
            airline_col=ctx.airline_col,
            top_n=ctx.top_n,
            start_date=ctx.start_date,
            end_date=ctx.end_date,
        )

        # ── Network map ──
        st.header("US domestic network map")
        map_airline_col = (
            "operating_airline" if (ctx.operating_only and ctx.has_operating) else "airline"
        )
        map_airlines_g = sorted(ctx.df[map_airline_col].dropna().unique().tolist())
        map_airline_display_g: list[str] = []
        map_display_to_code_g: dict[str, str] = {}
        for code in map_airlines_g:
            display = (
                f"{code} - {info.name}"
                if (info := get_airline(code)) and info.name
                else code
            )
            map_airline_display_g.append(display)
            map_display_to_code_g[display] = code

        sel_map_airlines_g = st.multiselect(
            "Filter by airlines",
            options=map_airline_display_g,
            default=[],
            help="Leave empty to show all. Select airlines to compare with distinct colors.",
            key="overview_g_map_airlines",
        )
        sel_map_codes_g = [
            map_display_to_code_g[d]
            for d in sel_map_airlines_g
            if d in map_display_to_code_g
        ]
        _render_network_map(ctx.df, map_airline_col, sel_map_codes_g, ctx.geo_scope, ctx.top_n)

    else:
        # ── Focus mode: top destinations ──
        dest_codes = get_destination_column(ctx.df, ctx.direction, ctx.focus_airport)
        dest_counts = dest_codes.value_counts()

        airport_rows = []
        for iata, count in dest_counts.head(ctx.top_n).items():
            info = get_airport(iata)
            share = 100 * count / ctx.total_flights if ctx.total_flights > 0 else 0
            label = f"{iata} - {info.name}" if info and info.name else iata
            airport_rows.append(
                {"Label": label, "Flights": count, "Share (%)": round(share, 1)}
            )
        airport_df = pd.DataFrame(
            airport_rows, columns=["Label", "Flights", "Share (%)"]
        )

        city_counts: dict[str, int] = {}
        for iata, count in dest_counts.items():
            info = get_airport(iata)
            city = info.city if info and info.city else iata
            city_counts[city] = city_counts.get(city, 0) + count
        city_sorted = sorted(city_counts.items(), key=lambda x: -x[1])[:ctx.top_n]
        city_df = pd.DataFrame(
            [{"City": c, "Flights": n} for c, n in city_sorted],
            columns=["City", "Flights"],
        )
        city_df["Share (%)"] = (
            (100 * city_df["Flights"] / ctx.total_flights).round(1)
            if ctx.total_flights
            else 0.0
        )

        if ctx.show_country:
            country_counts: dict[str, int] = {}
            for iata, count in dest_counts.items():
                info = get_airport(iata)
                country = info.country if info and info.country else iata
                country_counts[country] = country_counts.get(country, 0) + count
            country_sorted = sorted(country_counts.items(), key=lambda x: -x[1])[
                :ctx.top_n
            ]
            country_df = pd.DataFrame(
                [{"Country": c, "Flights": n} for c, n in country_sorted],
                columns=["Country", "Flights"],
            )
            country_df["Share (%)"] = (
                (100 * country_df["Flights"] / ctx.total_flights).round(1)
                if ctx.total_flights
                else 0.0
            )

        fig_apt = px.bar(
            airport_df,
            x="Flights",
            y="Label",
            orientation="h",
            color="Flights",
            color_continuous_scale="Greens",
            text=airport_df["Share (%)"].apply(lambda x: f"{x}%"),
        )
        fig_apt.update_traces(textposition="outside")
        fig_apt.update_layout(
            height=chart_h,
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
        )
        _start_flight_count_axis_at_zero(fig_apt, "x")

        fig_city = px.bar(
            city_df,
            x="Flights",
            y="City",
            orientation="h",
            color="Flights",
            color_continuous_scale="Oranges",
            text=city_df["Share (%)"].apply(lambda x: f"{x}%"),
        )
        fig_city.update_traces(textposition="outside")
        fig_city.update_layout(
            height=chart_h,
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
        )
        _start_flight_count_axis_at_zero(fig_city, "x")

        if ctx.show_country:
            fig_country = px.bar(
                country_df,
                x="Flights",
                y="Country",
                orientation="h",
                color="Flights",
                color_continuous_scale="Purples",
                text=country_df["Share (%)"].apply(lambda x: f"{x}%"),
            )
            fig_country.update_traces(textposition="outside")
            fig_country.update_layout(
                height=chart_h,
                yaxis={"categoryorder": "total ascending"},
                showlegend=False,
            )
            _start_flight_count_axis_at_zero(fig_country, "x")

        r1c1, r1c2 = st.columns(2)
        with r1c1:
            st.subheader("Top airlines by flight count")
            st.plotly_chart(fig_airlines, width="stretch")
        with r1c2:
            st.subheader("Top destinations by airport")
            st.plotly_chart(fig_apt, width="stretch")

        if ctx.show_country:
            r2c1, r2c2 = st.columns(2)
            with r2c1:
                st.subheader("Top destinations by city")
                st.plotly_chart(fig_city, width="stretch")
            with r2c2:
                st.subheader("Top destinations by country")
                st.plotly_chart(fig_country, width="stretch")
        else:
            st.subheader("Top destinations by city")
            st.plotly_chart(fig_city, width="stretch")

        _render_overview_flights_per_day(
            ctx.df,
            airline_col=ctx.airline_col,
            top_n=ctx.top_n,
            start_date=ctx.start_date,
            end_date=ctx.end_date,
        )

        # ── Interactive Map ──
        st.header("Interactive map: flight flow by destination")

        map_airline_col = (
            "operating_airline" if (ctx.operating_only and ctx.has_operating) else "airline"
        )
        map_airlines = sorted(ctx.df[map_airline_col].dropna().unique().tolist())
        map_airline_display: list[str] = []
        map_display_to_code: dict[str, str] = {}
        for code in map_airlines:
            display = (
                f"{code} - {info.name}"
                if (info := get_airline(code)) and info.name
                else code
            )
            map_airline_display.append(display)
            map_display_to_code[display] = code

        _dest_codes_for_countries = get_destination_column(
            ctx.df, ctx.direction, ctx.focus_airport
        )
        _country_set: set[str] = set()
        _iata_to_country: dict[str, str] = {}
        for _iata in _dest_codes_for_countries.unique():
            _info = get_airport(_iata)
            if _info and _info.country:
                _country_set.add(_info.country)
                _iata_to_country[_iata] = _info.country
        map_country_options = sorted(_country_set)

        if ctx.show_country:
            col_map_by, col_map_airline, col_map_country = st.columns(3)
        else:
            col_map_by, col_map_airline = st.columns(2)
            col_map_country = None

        with col_map_by:
            map_point_opts = ["City (airport)"]
            if ctx.show_country:
                map_point_opts.append("Country")
            map_point_by = st.radio(
                "Map points by",
                options=map_point_opts,
                index=0,
                horizontal=True,
                help="Show each destination as a precise city/airport, or aggregate by country.",
            )
        with col_map_airline:
            sel_map_airlines = st.multiselect(
                "Filter by airlines",
                options=map_airline_display,
                default=[],
                help="Leave empty to show all. Select airlines to compare on map with distinct colors.",
            )
        if col_map_country is not None:
            with col_map_country:
                sel_map_countries = st.multiselect(
                    "Filter by country",
                    options=map_country_options,
                    default=[],
                    help="Leave empty to show all. Select countries to show only routes to those countries.",
                )
        else:
            sel_map_countries = []

        map_by_country = map_point_by == "Country"
        sel_map_codes = [
            map_display_to_code[d]
            for d in sel_map_airlines
            if d in map_display_to_code
        ]

        if sel_map_countries:
            _allowed_iatas = {
                iata
                for iata, c in _iata_to_country.items()
                if c in sel_map_countries
            }
            if ctx.direction == "Departures":
                _country_mask = ctx.df["destination"].isin(_allowed_iatas)
            elif ctx.direction == "Arrivals":
                _country_mask = ctx.df["origin"].isin(_allowed_iatas)
            else:
                _country_mask = ctx.df["destination"].isin(_allowed_iatas) | ctx.df[
                    "origin"
                ].isin(_allowed_iatas)
            df_map = ctx.df[_country_mask]
        else:
            df_map = ctx.df

        _render_flight_map(
            df_map,
            ctx.direction,
            ctx.focus_airport,
            ctx.focus_lat,
            ctx.focus_lon,
            map_by_country,
            sel_map_codes,
            map_airline_col,
            ctx.geo_scope,
            top_arcs_n=ctx.top_n,
        )
