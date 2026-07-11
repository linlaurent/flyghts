"""Dashboard section: Route deep dive."""

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
from ..formatting import (
    RouteCityKey,
    _airport_city_key,
    _build_region_route_selection,
    _city_key_display,
    _city_key_label,
    _city_pair_airport_counts,
    _multi_airport_city_keys_for_iatas,
    _route_label,
)
from ..maps import (
    _render_flight_map,
    _render_region_airport_map,
    _render_route_top_airports_tab,
)


def render_route_dive(ctx: DashboardContext) -> None:
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

    st.header("Route deep dive")

    route_mode_options = ["By airport", "By city", "By province"]
    if show_country:
        route_mode_options.append("By country")
    route_mode = st.radio(
        "Route by",
        options=route_mode_options,
        index=0,
        horizontal=True,
        help="Dive into a single airport route, group airports by city or province/state, or aggregate all routes to a country.",
        key="route_dive_by",
    )
    route_by_city = route_mode == "By city"
    route_by_country = route_mode == "By country"
    route_by_province = route_mode == "By province"
    route_multi_airport_only = False
    if route_by_city or route_by_province or route_by_country:
        _route_group_label = {
            "By city": "cities",
            "By province": "provinces",
            "By country": "countries",
        }[route_mode]
        route_multi_airport_only = st.checkbox(
            f"Only {_route_group_label} with multiple airports",
            value=True,
            help=(
                f"Show only {_route_group_label} that have multiple airports "
                "in the filtered data."
            ),
            key=f"route_dive_multi_airport_only_{route_mode}",
        )

    route_display_options: list[str] = []
    route_str_to_airports: dict[str, tuple[str, str]] = {}
    route_str_to_city_keys: dict[str, tuple[RouteCityKey, RouteCityKey]] = {}
    route_str_to_region: dict[str, str] = {}
    _route_region_airports: dict[str, set[str]] = {}
    _route_region_country: dict[str, str] = {}
    if route_by_country:
        (
            route_display_options,
            route_str_to_region,
            _route_region_airports,
            _route_region_country,
        ) = _build_region_route_selection(
            df,
            direction,
            focus_airport,
            "country",
            multi_airport_only=route_multi_airport_only,
        )
    elif route_by_province:
        (
            route_display_options,
            route_str_to_region,
            _route_region_airports,
            _route_region_country,
        ) = _build_region_route_selection(
            df,
            direction,
            focus_airport,
            "province",
            multi_airport_only=route_multi_airport_only,
        )
    elif route_by_city:
        _route_city_counts: dict[tuple[RouteCityKey, RouteCityKey], int] = {}
        _route_city_iatas: dict[RouteCityKey, set[str]] = {}
        for origin, destination in df[["origin", "destination"]].itertuples(
            index=False
        ):
            origin_key = _airport_city_key(origin)
            destination_key = _airport_city_key(destination)
            _route_city_iatas.setdefault(origin_key, set()).add(origin)
            _route_city_iatas.setdefault(destination_key, set()).add(destination)
            city_pair = tuple(sorted((origin_key, destination_key)))
            _route_city_counts[city_pair] = _route_city_counts.get(city_pair, 0) + 1
        focus_city_key = _airport_city_key(focus_airport) if focus_airport else None
        for (city_a, city_b), count in sorted(
            _route_city_counts.items(), key=lambda x: -x[1]
        ):
            if route_multi_airport_only:
                if focus_city_key and not global_mode:
                    if city_a == focus_city_key or city_b == focus_city_key:
                        other_city = city_b if city_a == focus_city_key else city_a
                        if len(_route_city_iatas.get(other_city, set())) < 2:
                            continue
                    elif (
                        len(_route_city_iatas.get(city_a, set())) < 2
                        and len(_route_city_iatas.get(city_b, set())) < 2
                    ):
                        continue
                elif (
                    len(_route_city_iatas.get(city_a, set())) < 2
                    and len(_route_city_iatas.get(city_b, set())) < 2
                ):
                    continue
            if global_mode or not focus_city_key:
                label = (
                    f"{_city_key_display(city_a, _route_city_iatas.get(city_a))}"
                    f" ↔ {_city_key_display(city_b, _route_city_iatas.get(city_b))}"
                    f" — {count:,} flights"
                )
            elif city_a == focus_city_key or city_b == focus_city_key:
                other_city = city_b if city_a == focus_city_key else city_a
                label = (
                    f"{_city_key_display(other_city, _route_city_iatas.get(other_city))}"
                    f" - {count:,} flights"
                )
            else:
                label = (
                    f"{_city_key_display(city_a, _route_city_iatas.get(city_a))}"
                    f" ↔ {_city_key_display(city_b, _route_city_iatas.get(city_b))}"
                    f" — {count:,} flights"
                )
            route_display_options.append(label)
            route_str_to_city_keys[label] = (city_a, city_b)
    else:
        route_series = df["origin"] + "-" + df["destination"]
        route_pairs = route_series.apply(
            lambda s: "-".join(sorted(s.split("-", 1))) if "-" in s else s
        )
        route_counts = route_pairs.value_counts()
        for route_str, count in route_counts.items():
            parts = route_str.split("-", 1)
            if len(parts) == 2:
                a, b = parts[0], parts[1]
                if global_mode:
                    a_info = get_airport(a)
                    b_info = get_airport(b)
                    a_city = a_info.city if a_info and a_info.city else a
                    b_city = b_info.city if b_info and b_info.city else b
                    label = f"{a} ({a_city}) ↔ {b} ({b_city}) — {count:,} flights"
                else:
                    other = b if a == focus_airport else a
                    info = get_airport(other)
                    name = info.name if info and info.name else other
                    label = f"{other} - {name} - {count:,} flights"
                route_display_options.append(label)
                route_str_to_airports[label] = (a, b)

    col_search_r, col_select_r = st.columns(2)
    with col_search_r:
        if route_by_country:
            route_search = st.text_input(
                "Search routes by country name",
                placeholder="e.g. Japan, United States",
                help="Filter the route list by typing a country name.",
                key="route_dive_search",
            )
        elif route_by_province:
            route_search = st.text_input(
                "Search routes by province or state name",
                placeholder="e.g. Guangdong Province, Georgia, California",
                help="Filter the route list by typing a province, state, or region name.",
                key="route_dive_search",
            )
        elif route_by_city:
            route_search = st.text_input(
                "Search routes by city, country, or airport code",
                placeholder="e.g. New York, Los Angeles, JFK",
                help="Filter the route list by typing a city, country, or airport code.",
                key="route_dive_search",
            )
        else:
            route_search = st.text_input(
                "Search routes by airport code or name",
                placeholder="e.g. LAX, Atlanta, SFO",
                help="Filter the route list by typing airport code (IATA) or airport name.",
                key="route_dive_search",
            )
    search_lower = route_search.strip().lower()
    if search_lower:
        filtered_routes = [
            r for r in route_display_options if search_lower in r.lower()
        ]
    else:
        filtered_routes = route_display_options

    if not filtered_routes:
        st.info(
            "No routes match your search."
            if search_lower
            else "No routes in the filtered data."
        )
    else:
        with col_select_r:
            sel_route_display = st.selectbox(
                "Select route",
                options=filtered_routes,
                index=0,
                help="Explore statistics for a route (both directions grouped).",
            )

        if route_by_country or route_by_province:
            sel_region = route_str_to_region.get(sel_route_display, "")
            region_iatas = _route_region_airports.get(sel_region, set())
            df_route = df[
                df["origin"].isin(region_iatas)
                | df["destination"].isin(region_iatas)
            ]
        elif route_by_city:
            city_a, city_b = route_str_to_city_keys.get(
                sel_route_display, (("", ""), ("", ""))
            )
            _origin_city_keys = df["origin"].apply(_airport_city_key)
            _destination_city_keys = df["destination"].apply(_airport_city_key)
            mask_city_pair = (
                (_origin_city_keys == city_a) & (_destination_city_keys == city_b)
            ) | ((_origin_city_keys == city_b) & (_destination_city_keys == city_a))
            df_route = df[mask_city_pair]
        else:
            airport_a, airport_b = route_str_to_airports.get(
                sel_route_display, ("", "")
            )
            mask_both = (
                (df["origin"] == airport_a) & (df["destination"] == airport_b)
            ) | ((df["origin"] == airport_b) & (df["destination"] == airport_a))
            df_route = df[mask_both]

        if df_route.empty:
            st.info("No flights for this route in the selected filters.")
        else:
            _selected_multi_airport_city_keys: list[RouteCityKey] = []
            _airport_compare_city_keys: list[RouteCityKey] = []
            _airport_compare_province_iatas: set[str] = set()
            if route_by_country:
                route_label = sel_region
                _airport_compare_city_keys = _multi_airport_city_keys_for_iatas(
                    _route_region_airports.get(sel_region, set())
                )
            elif route_by_province:
                country = _route_region_country.get(sel_region, "")
                route_label = (
                    f"{sel_region}, {country}" if country else sel_region
                )
                _airport_compare_province_iatas = _route_region_airports.get(
                    sel_region, set()
                )
            elif route_by_city:
                if global_mode:
                    route_label = (
                        f"{_city_key_label(city_a)} ↔ {_city_key_label(city_b)}"
                    )
                else:
                    focus_city_key = (
                        _airport_city_key(focus_airport) if focus_airport else None
                    )
                    if focus_city_key and (
                        city_a == focus_city_key or city_b == focus_city_key
                    ):
                        other_city = city_b if city_a == focus_city_key else city_a
                        route_label = _city_key_label(other_city)
                    else:
                        route_label = (
                            f"{_city_key_label(city_a)} ↔ {_city_key_label(city_b)}"
                        )
                _selected_multi_airport_city_keys = [
                    city_key
                    for city_key in dict.fromkeys([city_a, city_b])
                    if len(_route_city_iatas.get(city_key, set())) >= 2
                ]
                _airport_compare_city_keys = _selected_multi_airport_city_keys
            elif global_mode:
                a_info = get_airport(airport_a)
                b_info = get_airport(airport_b)
                a_city = a_info.city if a_info and a_info.city else airport_a
                b_city = b_info.city if b_info and b_info.city else airport_b
                route_label = f"{airport_a} ({a_city}) ↔ {airport_b} ({b_city})"
            else:
                other = airport_b if airport_a == focus_airport else airport_a
                other_info = get_airport(other)
                name = other_info.name if other_info and other_info.name else other
                route_label = f"{other} - {name}"
            st.subheader(route_label)

            n_route = len(df_route)
            pct_route = 100 * n_route / total_flights if total_flights > 0 else 0
            m1, m2 = st.columns(2)
            with m1:
                st.metric("Total flights on route", f"{n_route:,}")
            with m2:
                st.metric("Share of traffic", f"{pct_route:.1f}%")

            _show_airport_compare = bool(_airport_compare_city_keys) or (
                route_by_province and len(_airport_compare_province_iatas) >= 2
            )

            _route_tab_names: list[str] = []
            if route_by_country or route_by_province or route_by_city:
                _route_tab_names.append("Top airports")
            if _show_airport_compare:
                _route_tab_names.append("Airport comparison")
            _route_tab_names += [
                "Top airlines",
                "Flights over time",
                "Flights by hour",
                "Flights by weekday",
            ]
            if not is_us:
                _route_tab_names.append("Cargo vs passenger")
            _route_tabs = st.tabs(_route_tab_names)
            _idx = 0
            if route_by_country or route_by_province or route_by_city:
                tab_route_top_airports = _route_tabs[_idx]
                _idx += 1
            else:
                tab_route_top_airports = None
            if _show_airport_compare:
                tab_route_airport_compare = _route_tabs[_idx]
                _idx += 1
            else:
                tab_route_airport_compare = None
            tab_route_airlines = _route_tabs[_idx]
            _idx += 1
            tab_route_time = _route_tabs[_idx]
            _idx += 1
            tab_route_hour = _route_tabs[_idx]
            _idx += 1
            tab_route_weekday = _route_tabs[_idx]
            _idx += 1
            tab_route_cargo = _route_tabs[_idx] if not is_us else None

            if tab_route_top_airports is not None:
                with tab_route_top_airports:
                    if route_by_city:
                        _top_airport_counts = _city_pair_airport_counts(
                            df_route, city_a, city_b
                        )
                    else:
                        _top_airport_counts = get_destination_column(
                            df_route, direction, focus_airport
                        ).value_counts()
                    _map_exclude = (
                        {focus_airport} if focus_airport else set()
                    )
                    _render_route_top_airports_tab(
                        df_route,
                        _top_airport_counts,
                        direction,
                        focus_airport,
                        geo_scope,
                        top_n,
                        start_date,
                        end_date,
                        map_exclude_iatas=_map_exclude,
                    )

            if tab_route_airport_compare is not None:
                with tab_route_airport_compare:
                    if route_by_province:
                        _compare_caption = (
                            "Compare how flights are split across airports "
                            "within this province."
                        )
                        _compare_empty = (
                            "No airport traffic is available for this province."
                        )
                        _share_scope = "province"
                    else:
                        _compare_caption = (
                            "Compare how flights are split across airports within "
                            "multi-airport cities."
                        )
                        _compare_empty = (
                            "No multi-airport city traffic is available for this route."
                        )
                        _share_scope = "city"
                    st.caption(_compare_caption)
                    _airport_compare_rows = []
                    for row in df_route.itertuples(index=False):
                        for airport in (row.origin, row.destination):
                            if route_by_province:
                                if airport not in _airport_compare_province_iatas:
                                    continue
                                group_label = sel_region
                            else:
                                city_key = _airport_city_key(airport)
                                if city_key not in _airport_compare_city_keys:
                                    continue
                                group_label = _city_key_label(city_key)
                            info = get_airport(airport)
                            _airport_compare_rows.append(
                                {
                                    "Date": row.date.date(),
                                    "Group": group_label,
                                    "Airport": airport,
                                    "Name": info.name if info else airport,
                                    "Airline": getattr(row, airline_col),
                                }
                            )
                    _airport_compare_df = pd.DataFrame(_airport_compare_rows)
                    if _airport_compare_df.empty:
                        st.caption(_compare_empty)
                    else:
                        _airport_counts = (
                            _airport_compare_df.groupby(
                                ["Group", "Airport", "Name"], as_index=False
                            )
                            .size()
                            .rename(columns={"size": "Flights"})
                        )
                        _airport_counts["Group total"] = _airport_counts.groupby(
                            "Group"
                        )["Flights"].transform("sum")
                        _airport_counts["Share (%)"] = (
                            100
                            * _airport_counts["Flights"]
                            / _airport_counts["Group total"]
                        ).round(1)
                        _airport_counts["Share label"] = _airport_counts[
                            "Share (%)"
                        ].apply(lambda x: f"{x}%")
                        _airport_counts["Label"] = (
                            _airport_counts["Airport"]
                            + " - "
                            + _airport_counts["Name"]
                        )
                        fig_airport_compare = px.bar(
                            _airport_counts.sort_values("Flights"),
                            x="Flights",
                            y="Label",
                            color="Group",
                            orientation="h",
                            labels={"Flights": "Number of flights"},
                            text="Share label",
                            custom_data=["Group", "Share (%)"],
                        )
                        _share_hover = (
                            "Province share"
                            if _share_scope == "province"
                            else "City share"
                        )
                        fig_airport_compare.update_traces(
                            hovertemplate=f"%{{customdata[0]}}<br>%{{y}}<br>Flights: %{{x:,}}<br>{_share_hover}: %{{customdata[1]}}%<extra></extra>",
                            textposition="outside",
                        )
                        fig_airport_compare.update_layout(
                            height=300 + len(_airport_counts) * 16,
                            yaxis={"categoryorder": "total ascending"},
                        )
                        _start_flight_count_axis_at_zero(fig_airport_compare, "x")
                        st.plotly_chart(fig_airport_compare, width="stretch")

                        _airport_daily = (
                            _airport_compare_df.groupby(
                                ["Date", "Group", "Airport"], as_index=False
                            )
                            .size()
                            .rename(columns={"size": "Flights"})
                        )
                        _airport_daily["Airport label"] = (
                            _airport_daily["Group"]
                            + " | "
                            + _airport_daily["Airport"]
                        )
                        _airport_daily = _complete_daily_series(
                            _airport_daily,
                            date_col="Date",
                            value_cols=["Flights"],
                            start_date=start_date,
                            end_date=end_date,
                            group_cols=["Group", "Airport", "Airport label"],
                        )
                        fig_airport_daily = px.line(
                            _airport_daily,
                            x="Date",
                            y="Flights",
                            color="Airport label",
                            labels={"Flights": "Number of flights"},
                        )
                        fig_airport_daily.update_layout(
                            height=350,
                            title="Flights over time by airport",
                        )
                        _start_flight_count_axis_at_zero(fig_airport_daily, "y")
                        st.plotly_chart(fig_airport_daily, width="stretch")

                        _airport_daily_share = _airport_daily.copy()
                        _airport_daily_share["Group total"] = (
                            _airport_daily_share.groupby(["Date", "Group"])[
                                "Flights"
                            ].transform("sum")
                        )
                        _airport_daily_share["Share (%)"] = np.where(
                            _airport_daily_share["Group total"] > 0,
                            100
                            * _airport_daily_share["Flights"]
                            / _airport_daily_share["Group total"],
                            0,
                        ).round(1)
                        _share_y_label = (
                            "Share of province flights (%)"
                            if _share_scope == "province"
                            else "Share of city flights (%)"
                        )
                        _share_chart_title = (
                            "Share of province flights per day by airport"
                            if _share_scope == "province"
                            else "Share of city flights per day by airport"
                        )
                        _share_total_label = (
                            "Province total"
                            if _share_scope == "province"
                            else "City total"
                        )
                        fig_airport_daily_share = px.line(
                            _airport_daily_share,
                            x="Date",
                            y="Share (%)",
                            color="Airport label",
                            labels={"Share (%)": _share_y_label},
                            custom_data=["Flights", "Group total"],
                        )
                        fig_airport_daily_share.update_traces(
                            hovertemplate=f"%{{fullData.name}}<br>%{{x}}<br>Flights: %{{customdata[0]:,}}<br>{_share_total_label}: %{{customdata[1]:,}}<br>Share: %{{y}}%<extra></extra>",
                        )
                        fig_airport_daily_share.update_layout(
                            height=350,
                            title=_share_chart_title,
                            yaxis=dict(title=_share_y_label, range=[0, 100]),
                        )
                        st.plotly_chart(fig_airport_daily_share, width="stretch")

                        _airport_airline = (
                            _airport_compare_df.groupby(
                                ["Group", "Airport", "Airline"], as_index=False
                            )
                            .size()
                            .rename(columns={"size": "Flights"})
                        )
                        _airport_airline["Airline name"] = _airport_airline[
                            "Airline"
                        ].apply(
                            lambda c: get_airline(c).name if get_airline(c) else c
                        )
                        _airport_airline["Airport label"] = (
                            _airport_airline["Group"]
                            + " | "
                            + _airport_airline["Airport"]
                        )
                        _airport_airline = _airport_airline.sort_values(
                            "Flights", ascending=False
                        ).head(top_n)
                        fig_airport_airline = px.bar(
                            _airport_airline,
                            x="Flights",
                            y="Airport label",
                            color="Airline name",
                            orientation="h",
                            labels={"Flights": "Number of flights"},
                        )
                        fig_airport_airline.update_layout(
                            height=300 + len(_airport_airline) * 12,
                            title="Top airline contributions by airport",
                            yaxis={"categoryorder": "total ascending"},
                        )
                        _start_flight_count_axis_at_zero(fig_airport_airline, "x")
                        st.plotly_chart(fig_airport_airline, width="stretch")

                        _compare_table = _airport_counts.rename(
                            columns={"Group": "Province" if route_by_province else "City"}
                        )
                        _render_aggrid(
                            _compare_table[
                                [
                                    "Province" if route_by_province else "City",
                                    "Airport",
                                    "Name",
                                    "Flights",
                                    "Share (%)",
                                ]
                            ]
                        )

            with tab_route_airlines:
                airline_counts_route = df_route[airline_col].value_counts()
                total_on_route = len(df_route)
                airline_rows = []
                for icao, count in airline_counts_route.head(top_n).items():
                    info = get_airline(icao)
                    name = info.name if info else icao
                    share = (
                        100 * count / total_on_route if total_on_route > 0 else 0
                    )
                    airline_rows.append(
                        {
                            "Airline": name,
                            "ICAO": icao,
                            "Flights": count,
                            "Share (%)": round(share, 1),
                        }
                    )
                airline_route_df = pd.DataFrame(
                    airline_rows,
                    columns=["Airline", "ICAO", "Flights", "Share (%)"],
                )
                if not airline_route_df.empty:
                    fig_route_airlines = px.bar(
                        airline_route_df,
                        x="Flights",
                        y="Airline",
                        orientation="h",
                        color="Share (%)",
                        color_continuous_scale="Viridis",
                        range_color=[0, 100],
                        labels={
                            "Flights": "Number of flights",
                            "Share (%)": "Share (%)",
                        },
                        text=airline_route_df["Share (%)"].apply(lambda x: f"{x}%"),
                    )
                    fig_route_airlines.update_layout(
                        height=300 + min(top_n, len(airline_route_df)) * 12,
                        yaxis={"categoryorder": "total ascending"},
                        showlegend=False,
                    )
                    _start_flight_count_axis_at_zero(fig_route_airlines, "x")
                    fig_route_airlines.update_traces(textposition="outside")
                    st.plotly_chart(fig_route_airlines, width="stretch")

                    top_airlines_route = set(airline_counts_route.head(top_n).index)
                    by_date_airline = (
                        df_route.groupby([df_route["date"].dt.date, airline_col])
                        .size()
                        .reset_index(name="Flights")
                    )
                    by_date_airline.columns = ["Date", "ICAO", "Flights"]
                    total_per_date = df_route.groupby(
                        df_route["date"].dt.date
                    ).size()
                    by_date_airline = by_date_airline[
                        by_date_airline["ICAO"].isin(top_airlines_route)
                    ]
                    by_date_airline = by_date_airline.merge(
                        total_per_date.rename("Total"),
                        left_on="Date",
                        right_index=True,
                    )
                    by_date_airline["Share (%)"] = (
                        100 * by_date_airline["Flights"] / by_date_airline["Total"]
                    ).round(1)
                    by_date_airline["Airline"] = by_date_airline["ICAO"].apply(
                        lambda c: get_airline(c).name if get_airline(c) else c
                    )
                    if not by_date_airline.empty:
                        by_date_airline = _complete_daily_series(
                            by_date_airline,
                            date_col="Date",
                            value_cols=["Flights", "Total", "Share (%)"],
                            start_date=start_date,
                            end_date=end_date,
                            group_cols=["ICAO", "Airline"],
                        )
                        fig_share_day = px.line(
                            by_date_airline,
                            x="Date",
                            y="Share (%)",
                            color="Airline",
                            labels={"Share (%)": "Share (%)"},
                            custom_data=["Flights", "Total", "Airline"],
                        )
                        fig_share_day.update_traces(
                            hovertemplate="%{customdata[2]}<br>%{x}<br>Flights: %{customdata[0]:,}<br>Total (denom): %{customdata[1]:,}<br>Share: %{y}%<extra></extra>",
                        )
                        fig_share_day.update_layout(
                            height=350,
                            title="Share of traffic (%) over time by airline",
                            yaxis=dict(title="Share (%)"),
                        )
                        st.plotly_chart(fig_share_day, width="stretch")

                _render_aggrid(
                    airline_route_df[["Airline", "ICAO", "Flights", "Share (%)"]]
                    if not airline_route_df.empty
                    else pd.DataFrame()
                )

            with tab_route_time:
                by_date_route = (
                    df_route.groupby(df_route["date"].dt.date)
                    .size()
                    .reset_index(name="Flights")
                )
                by_date_route.columns = ["Date", "Flights"]
                if not by_date_route.empty:
                    total_by_date = (
                        df.groupby(df["date"].dt.date)
                        .size()
                        .reset_index(name="Total")
                    )
                    total_by_date.columns = ["Date", "Total"]
                    share_route_df = by_date_route.merge(
                        total_by_date, on="Date", how="left"
                    )
                    share_route_df["Share"] = (
                        100 * share_route_df["Flights"] / share_route_df["Total"]
                    ).fillna(0)
                    share_route_df = _complete_daily_series(
                        share_route_df,
                        date_col="Date",
                        value_cols=["Flights", "Total", "Share"],
                        start_date=start_date,
                        end_date=end_date,
                    )

                    fig_route_time = go.Figure()
                    fig_route_time.add_trace(
                        go.Scatter(
                            x=share_route_df["Date"],
                            y=share_route_df["Flights"],
                            name="Flights",
                            line=dict(color="#1f77b4"),
                            mode="lines",
                        )
                    )
                    fig_route_time.add_trace(
                        go.Scatter(
                            x=share_route_df["Date"],
                            y=share_route_df["Share"],
                            name="Share of traffic (%)",
                            yaxis="y2",
                            line=dict(color="#ff7f0e"),
                            mode="lines",
                        )
                    )
                    fig_route_time.update_layout(
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
                    _start_flight_count_axis_at_zero(fig_route_time, "y")
                    st.plotly_chart(fig_route_time, width="stretch")

                    top_airlines_route = set(airline_counts_route.head(top_n).index)
                    by_date_airline_time = (
                        df_route.groupby([df_route["date"].dt.date, airline_col])
                        .size()
                        .reset_index(name="Flights")
                    )
                    by_date_airline_time.columns = ["Date", "ICAO", "Flights"]
                    by_date_airline_time = by_date_airline_time[
                        by_date_airline_time["ICAO"].isin(top_airlines_route)
                    ]
                    total_per_date_route = (
                        df_route.groupby(df_route["date"].dt.date)
                        .size()
                        .rename("Total")
                    )
                    by_date_airline_time = by_date_airline_time.merge(
                        total_per_date_route,
                        left_on="Date",
                        right_index=True,
                        how="left",
                    )
                    by_date_airline_time["Airline"] = by_date_airline_time[
                        "ICAO"
                    ].apply(lambda c: get_airline(c).name if get_airline(c) else c)
                    by_date_airline_time = _complete_daily_series(
                        by_date_airline_time,
                        date_col="Date",
                        value_cols=["Flights", "Total"],
                        start_date=start_date,
                        end_date=end_date,
                        group_cols=["ICAO", "Airline"],
                    )
                    if not by_date_airline_time.empty:
                        fig_count_day = px.line(
                            by_date_airline_time,
                            x="Date",
                            y="Flights",
                            color="Airline",
                            labels={"Flights": "Number of flights"},
                            custom_data=["Total", "Airline"],
                        )
                        fig_count_day.update_traces(
                            hovertemplate="%{customdata[1]}<br>%{x}<br>Flights: %{y:,}<br>Total (denom): %{customdata[0]:,}<extra></extra>",
                        )
                        fig_count_day.update_layout(
                            height=350,
                            title="Flights over time by airline",
                        )
                        _start_flight_count_axis_at_zero(fig_count_day, "y")
                        st.plotly_chart(fig_count_day, width="stretch")
                else:
                    st.caption("No date data.")

            with tab_route_hour:
                if not global_mode:
                    st.caption(
                        f"Departure time for flights from {focus_airport}; "
                        f"arrival time for flights to {focus_airport}."
                    )
                if "scheduled_time" in df_route.columns:
                    df_route_hour = df_route.dropna(subset=["scheduled_time"])
                    df_route_hour = df_route_hour.copy()
                    df_route_hour["hour"] = pd.to_datetime(
                        df_route_hour["scheduled_time"], errors="coerce"
                    ).dt.hour
                    df_route_hour = df_route_hour.dropna(subset=["hour"])
                    by_hour_route = (
                        df_route_hour.groupby("hour")
                        .size()
                        .reset_index(name="Flights")
                    )
                    if not by_hour_route.empty:
                        fig_route_hour = px.bar(
                            by_hour_route,
                            x="hour",
                            y="Flights",
                            labels={
                                "hour": "Hour of day",
                                "Flights": "Number of flights",
                            },
                        )
                        fig_route_hour.update_layout(height=350)
                        _start_flight_count_axis_at_zero(fig_route_hour, "y")
                        st.plotly_chart(fig_route_hour, width="stretch")
                    else:
                        st.caption("No scheduled time data for this route.")
                else:
                    st.caption("No scheduled_time column in data.")

            with tab_route_weekday:
                _rwd_order = [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday",
                ]
                _rwd = df_route.copy()
                _rwd["weekday"] = _rwd["date"].dt.day_name()
                _rwd_total = _rwd.groupby("weekday").size().rename("Total")
                _rwd_dates = (
                    _rwd.groupby("weekday")["date"]
                    .apply(lambda s: s.dt.date.nunique())
                    .rename("Days")
                )
                _rwd_df = pd.concat([_rwd_total, _rwd_dates], axis=1).reset_index()
                _rwd_df["Avg"] = (_rwd_df["Total"] / _rwd_df["Days"]).round(1)
                _rwd_df["weekday"] = pd.Categorical(
                    _rwd_df["weekday"], categories=_rwd_order, ordered=True
                )
                _rwd_df = _rwd_df.sort_values("weekday")
                if not _rwd_df.empty:
                    fig_rwd = px.bar(
                        _rwd_df,
                        x="weekday",
                        y="Avg",
                        labels={
                            "weekday": "Day of week",
                            "Avg": "Avg flights per day",
                        },
                        custom_data=["Total", "Days"],
                    )
                    fig_rwd.update_traces(
                        hovertemplate="%{x}<br>Avg: %{y}<br>Total: %{customdata[0]:,}<br>Days: %{customdata[1]}<extra></extra>",
                    )
                    fig_rwd.update_layout(height=350)
                    _start_flight_count_axis_at_zero(fig_rwd, "y")
                    st.plotly_chart(fig_rwd, width="stretch")
                else:
                    st.caption("No date data for weekday analysis.")

            if tab_route_cargo is not None:
                with tab_route_cargo:
                    if "cargo" in df_route.columns:
                        cargo_by_date_route = (
                            df_route.groupby([df_route["date"].dt.date, "cargo"])
                            .size()
                            .reset_index(name="Flights")
                        )
                        cargo_by_date_route["Type"] = cargo_by_date_route[
                            "cargo"
                        ].map({True: "Cargo", False: "Passenger"})
                        cargo_by_date_route = _complete_daily_series(
                            cargo_by_date_route,
                            date_col="date",
                            value_cols=["Flights"],
                            start_date=start_date,
                            end_date=end_date,
                            group_cols=["cargo", "Type"],
                        )
                        if not cargo_by_date_route.empty:
                            fig_route_cargo = px.line(
                                cargo_by_date_route,
                                x="date",
                                y="Flights",
                                color="Type",
                                labels={
                                    "date": "Date",
                                    "Flights": "Number of flights",
                                },
                                custom_data=["Type"],
                            )
                            fig_route_cargo.update_traces(
                                hovertemplate="%{customdata[0]}<br>%{x}<br>Flights: %{y:,}<extra></extra>",
                            )
                            fig_route_cargo.update_layout(height=350)
                            _start_flight_count_axis_at_zero(fig_route_cargo, "y")
                            st.plotly_chart(fig_route_cargo, width="stretch")
                        cargo_passenger_r = (df_route["cargo"] == False).sum()
                        cargo_cargo_r = (df_route["cargo"] == True).sum()
                        cargo_route_df = pd.DataFrame(
                            [
                                {"Type": "Passenger", "Flights": cargo_passenger_r},
                                {"Type": "Cargo", "Flights": cargo_cargo_r},
                            ]
                        )
                        _render_aggrid(cargo_route_df)
                    else:
                        st.caption("No cargo column in data.")
