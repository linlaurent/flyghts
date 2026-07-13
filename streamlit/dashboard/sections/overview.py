"""Dashboard section: Overview."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from flyghts.reference import get_airline, get_airport

from ..context import DashboardContext

from ..charts import (
    _render_overview_flights_per_day,
    _render_overview_flights_per_day_by_alliance,
    _start_flight_count_axis_at_zero,
)
from ..components import _render_aggrid
from ..data import get_destination_column, map_point_label_to_aggregate
from ..formatting import (
    ALLIANCE_ORDER,
    _airport_province,
    _alliance_label,
    with_alliance_column,
)
from ..maps import _render_flight_map, _render_network_map


def _top_alliances_chart(
    df: pd.DataFrame, airline_col: str, total_flights: int, chart_h: int
):
    """Build Top alliances bar chart from OPTD membership (not code-shares)."""
    df_a = with_alliance_column(df, airline_col)
    alliance_counts = df_a["alliance"].value_counts()
    rows = []
    for alliance_id in ALLIANCE_ORDER:
        count = int(alliance_counts.get(alliance_id, 0))
        if count <= 0 and alliance_id not in alliance_counts.index:
            continue
        share = 100 * count / total_flights if total_flights > 0 else 0
        rows.append(
            {
                "Alliance": _alliance_label(alliance_id),
                "Flights": count,
                "Share (%)": round(share, 1),
            }
        )
    # Include any unexpected keys
    for alliance_id, count in alliance_counts.items():
        if alliance_id in ALLIANCE_ORDER:
            continue
        share = 100 * count / total_flights if total_flights > 0 else 0
        rows.append(
            {
                "Alliance": _alliance_label(alliance_id),
                "Flights": int(count),
                "Share (%)": round(share, 1),
            }
        )
    alliance_df = pd.DataFrame(rows, columns=["Alliance", "Flights", "Share (%)"])
    if alliance_df.empty:
        return None, alliance_df
    fig = px.bar(
        alliance_df,
        x="Flights",
        y="Alliance",
        orientation="h",
        color="Flights",
        color_continuous_scale="Teal",
        text=alliance_df["Share (%)"].apply(lambda x: f"{x}%"),
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        height=chart_h, yaxis={"categoryorder": "total ascending"}, showlegend=False
    )
    _start_flight_count_axis_at_zero(fig, "x")
    return fig, alliance_df


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
    airline_df = pd.DataFrame(airline_rows, columns=["Airline", "Flights", "Share (%)"])
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
    fig_alliances, _alliance_df = _top_alliances_chart(
        ctx.df, ctx.airline_col, ctx.total_flights, chart_h
    )

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
        city_sorted_g = sorted(city_counts_g.items(), key=lambda x: -x[1])[: ctx.top_n]
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
            st.subheader("Top alliances by flight count")
            if fig_alliances is not None:
                st.plotly_chart(fig_alliances, width="stretch")
            else:
                st.caption("No alliance data for filtered flights.")

        r2c1, r2c2 = st.columns(2)
        with r2c1:
            st.subheader("Top airports by total traffic")
            st.plotly_chart(fig_apt_ov, width="stretch")
        with r2c2:
            st.subheader("Top cities by total traffic")
            st.plotly_chart(fig_city_g, width="stretch")

        st.subheader("Top routes (O-D pairs)")
        st.plotly_chart(fig_routes_ov, width="stretch")

        day_col, alliance_col = st.columns(2)
        with day_col:
            _render_overview_flights_per_day(
                ctx.df,
                airline_col=ctx.airline_col,
                top_n=ctx.top_n,
                start_date=ctx.start_date,
                end_date=ctx.end_date,
            )
        with alliance_col:
            _render_overview_flights_per_day_by_alliance(
                ctx.df,
                airline_col=ctx.airline_col,
                start_date=ctx.start_date,
                end_date=ctx.end_date,
            )

        # ── Network map ──
        st.header("US domestic network map")
        map_airline_col = (
            "operating_airline"
            if (ctx.operating_only and ctx.has_operating)
            else "airline"
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

        df_map_alliances_g = with_alliance_column(ctx.df, map_airline_col)
        present_alliances_g = [
            a for a in ALLIANCE_ORDER if a in set(df_map_alliances_g["alliance"])
        ]
        map_alliance_display_g = [_alliance_label(a) for a in present_alliances_g]
        map_alliance_to_id_g = {_alliance_label(a): a for a in present_alliances_g}

        col_map_airline_g, col_map_alliance_g = st.columns(2)
        with col_map_airline_g:
            sel_map_airlines_g = st.multiselect(
                "Filter by airlines",
                options=map_airline_display_g,
                default=[],
                help="Leave empty to show all. Select airlines to compare with distinct colors.",
                key="overview_g_map_airlines",
            )
        with col_map_alliance_g:
            sel_map_alliances_g = st.multiselect(
                "Filter by alliance",
                options=map_alliance_display_g,
                default=[],
                help="Leave empty to show all. Select alliances to show only member airlines.",
                key="overview_g_map_alliances",
            )
        sel_map_codes_g = [
            map_display_to_code_g[d]
            for d in sel_map_airlines_g
            if d in map_display_to_code_g
        ]
        sel_map_alliance_ids_g = [
            map_alliance_to_id_g[d]
            for d in sel_map_alliances_g
            if d in map_alliance_to_id_g
        ]
        df_network = ctx.df
        if sel_map_alliance_ids_g:
            df_network = with_alliance_column(df_network, map_airline_col)
            df_network = df_network[df_network["alliance"].isin(sel_map_alliance_ids_g)]
        _render_network_map(
            df_network, map_airline_col, sel_map_codes_g, ctx.geo_scope, ctx.top_n
        )

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
        city_sorted = sorted(city_counts.items(), key=lambda x: -x[1])[: ctx.top_n]
        city_df = pd.DataFrame(
            [{"City": c, "Flights": n} for c, n in city_sorted],
            columns=["City", "Flights"],
        )
        city_df["Share (%)"] = (
            (100 * city_df["Flights"] / ctx.total_flights).round(1)
            if ctx.total_flights
            else 0.0
        )

        province_counts: dict[str, int] = {}
        for iata, count in dest_counts.items():
            province = _airport_province(iata)
            province_counts[province] = province_counts.get(province, 0) + count
        province_sorted = sorted(province_counts.items(), key=lambda x: -x[1])[
            : ctx.top_n
        ]
        province_df = pd.DataFrame(
            [{"Province": p, "Flights": n} for p, n in province_sorted],
            columns=["Province", "Flights"],
        )
        province_df["Share (%)"] = (
            (100 * province_df["Flights"] / ctx.total_flights).round(1)
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
                : ctx.top_n
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

        fig_province = px.bar(
            province_df,
            x="Flights",
            y="Province",
            orientation="h",
            color="Flights",
            color_continuous_scale="Tealgrn",
            text=province_df["Share (%)"].apply(lambda x: f"{x}%"),
        )
        fig_province.update_traces(textposition="outside")
        fig_province.update_layout(
            height=chart_h,
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
        )
        _start_flight_count_axis_at_zero(fig_province, "x")

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
            st.subheader("Top alliances by flight count")
            if fig_alliances is not None:
                st.plotly_chart(fig_alliances, width="stretch")
            else:
                st.caption("No alliance data for filtered flights.")

        r2c1, r2c2 = st.columns(2)
        with r2c1:
            st.subheader("Top destinations by airport")
            st.plotly_chart(fig_apt, width="stretch")
        with r2c2:
            st.subheader("Top destinations by city")
            st.plotly_chart(fig_city, width="stretch")

        if ctx.show_country:
            r3c1, r3c2 = st.columns(2)
            with r3c1:
                st.subheader("Top destinations by province")
                st.plotly_chart(fig_province, width="stretch")
            with r3c2:
                st.subheader("Top destinations by country")
                st.plotly_chart(fig_country, width="stretch")
        else:
            st.subheader("Top destinations by province")
            st.plotly_chart(fig_province, width="stretch")

        day_col, alliance_col = st.columns(2)
        with day_col:
            _render_overview_flights_per_day(
                ctx.df,
                airline_col=ctx.airline_col,
                top_n=ctx.top_n,
                start_date=ctx.start_date,
                end_date=ctx.end_date,
            )
        with alliance_col:
            _render_overview_flights_per_day_by_alliance(
                ctx.df,
                airline_col=ctx.airline_col,
                start_date=ctx.start_date,
                end_date=ctx.end_date,
            )

        # ── Interactive Map ──
        st.header("Interactive map: flight flow by destination")

        map_airline_col = (
            "operating_airline"
            if (ctx.operating_only and ctx.has_operating)
            else "airline"
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

        df_map_alliances = with_alliance_column(ctx.df, map_airline_col)
        present_alliances = [
            a for a in ALLIANCE_ORDER if a in set(df_map_alliances["alliance"])
        ]
        map_alliance_display = [_alliance_label(a) for a in present_alliances]
        map_alliance_to_id = {_alliance_label(a): a for a in present_alliances}

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
            col_map_by, col_map_airline, col_map_alliance, col_map_country = st.columns(
                4
            )
        else:
            col_map_by, col_map_airline, col_map_alliance = st.columns(3)
            col_map_country = None

        with col_map_by:
            map_point_opts = ["City (airport)", "Province"]
            if ctx.show_country:
                map_point_opts.append("Country")
            map_point_by = st.radio(
                "Map points by",
                options=map_point_opts,
                index=0,
                horizontal=True,
                help="Show each destination as a precise city/airport, or aggregate by province/state or country.",
            )
        with col_map_airline:
            sel_map_airlines = st.multiselect(
                "Filter by airlines",
                options=map_airline_display,
                default=[],
                help="Leave empty to show all. Select airlines to compare on map with distinct colors.",
            )
        with col_map_alliance:
            sel_map_alliances = st.multiselect(
                "Filter by alliance",
                options=map_alliance_display,
                default=[],
                help="Leave empty to show all. Select alliances to show only member airlines.",
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

        map_aggregate_by = map_point_label_to_aggregate(map_point_by)
        sel_map_codes = [
            map_display_to_code[d] for d in sel_map_airlines if d in map_display_to_code
        ]
        sel_map_alliance_ids = [
            map_alliance_to_id[d] for d in sel_map_alliances if d in map_alliance_to_id
        ]

        if sel_map_countries:
            _allowed_iatas = {
                iata for iata, c in _iata_to_country.items() if c in sel_map_countries
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

        if sel_map_alliance_ids:
            df_map = with_alliance_column(df_map, map_airline_col)
            df_map = df_map[df_map["alliance"].isin(sel_map_alliance_ids)]

        _render_flight_map(
            df_map,
            ctx.direction,
            ctx.focus_airport,
            ctx.focus_lat,
            ctx.focus_lon,
            map_aggregate_by,
            sel_map_codes,
            map_airline_col,
            ctx.geo_scope,
            top_arcs_n=ctx.top_n,
        )
