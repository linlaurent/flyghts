"""Route deep dive section."""

import pandas as pd

import streamlit as st
from flyghts.reference import get_airport

from ... import action_logger as al
from ...context import DashboardContext
from ...formatting import (
    RouteCityKey,
    _airport_city_key,
    _build_region_route_selection,
    _city_key_display,
    _city_key_label,
    _multi_airport_city_keys_for_iatas,
)
from .drilldown import consume_drill_request, consume_pending_drill_match
from .tabs import render_route_tabs


def render_route_dive(ctx: DashboardContext) -> None:
    st.header("Route deep dive")

    consume_drill_request()

    route_mode_options = ["By airport", "By city", "By province"]
    if ctx.show_country:
        route_mode_options.append("By country")
    route_mode = al.radio(
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
        route_multi_airport_only = al.checkbox(
            f"Only {_route_group_label} with multiple airports",
            value=True,
            help=(
                f"Show only {_route_group_label} that have multiple airports "
                "in the filtered data."
            ),
            key=f"route_dive_multi_airport_only_{route_mode}",
        )

    route_display_options: list[str] = []
    sel_region = ""
    city_a = city_b = None
    airport_a = airport_b = ""
    _route_city_iatas: dict[RouteCityKey, set[str]] = {}
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
            ctx.df,
            ctx.direction,
            ctx.focus_airport,
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
            ctx.df,
            ctx.direction,
            ctx.focus_airport,
            "province",
            multi_airport_only=route_multi_airport_only,
        )
    elif route_by_city:
        _route_city_counts: dict[tuple[RouteCityKey, RouteCityKey], int] = {}
        _route_city_iatas: dict[RouteCityKey, set[str]] = {}
        for origin, destination in ctx.df[["origin", "destination"]].itertuples(
            index=False
        ):
            origin_key = _airport_city_key(origin)
            destination_key = _airport_city_key(destination)
            _route_city_iatas.setdefault(origin_key, set()).add(origin)
            _route_city_iatas.setdefault(destination_key, set()).add(destination)
            city_pair = tuple(sorted((origin_key, destination_key)))
            _route_city_counts[city_pair] = _route_city_counts.get(city_pair, 0) + 1
        focus_city_key = (
            _airport_city_key(ctx.focus_airport) if ctx.focus_airport else None
        )
        for (city_a, city_b), count in sorted(
            _route_city_counts.items(), key=lambda x: -x[1]
        ):
            if route_multi_airport_only:
                if focus_city_key and not ctx.global_mode:
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
            if ctx.global_mode or not focus_city_key:
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
        route_series = ctx.df["origin"] + "-" + ctx.df["destination"]
        route_pairs = route_series.apply(
            lambda s: "-".join(sorted(s.split("-", 1))) if "-" in s else s
        )
        route_counts = route_pairs.value_counts()
        for route_str, count in route_counts.items():
            parts = route_str.split("-", 1)
            if len(parts) == 2:
                a, b = parts[0], parts[1]
                if ctx.global_mode:
                    a_info = get_airport(a)
                    b_info = get_airport(b)
                    a_city = a_info.city if a_info and a_info.city else a
                    b_city = b_info.city if b_info and b_info.city else b
                    label = f"{a} ({a_city}) ↔ {b} ({b_city}) — {count:,} flights"
                else:
                    other = b if a == ctx.focus_airport else a
                    info = get_airport(other)
                    name = info.name if info and info.name else other
                    label = f"{other} - {name} - {count:,} flights"
            route_display_options.append(label)
            route_str_to_airports[label] = (a, b)

    col_search_r, col_select_r = st.columns(2)
    with col_search_r:
        if route_by_country:
            route_search = al.text_input(
                "Search routes by country name",
                placeholder="e.g. Japan, United States",
                help="Filter the route list by typing a country name.",
                key="route_dive_search",
            )
        elif route_by_province:
            route_search = al.text_input(
                "Search routes by province or state name",
                placeholder="e.g. Guangdong Province, Georgia, California",
                help="Filter the route list by typing a province, state, or region name.",
                key="route_dive_search",
            )
        elif route_by_city:
            route_search = al.text_input(
                "Search routes by city, country, or airport code",
                placeholder="e.g. New York, Los Angeles, JFK",
                help="Filter the route list by typing a city, country, or airport code.",
                key="route_dive_search",
            )
        else:
            route_search = al.text_input(
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

    pending_label = consume_pending_drill_match(
        route_str_to_region=route_str_to_region,
        route_str_to_city_keys=route_str_to_city_keys,
        route_str_to_airports=route_str_to_airports,
    )
    if pending_label and pending_label in filtered_routes:
        st.session_state["route_dive_selection"] = pending_label

    if not filtered_routes:
        st.info(
            "No routes match your search."
            if search_lower
            else "No routes in the filtered data."
        )
    else:
        with col_select_r:
            sel_route_display = al.selectbox(
                "Select route",
                options=filtered_routes,
                index=0,
                help="Explore statistics for a route (both directions grouped).",
                key="route_dive_selection",
            )

        if route_by_country or route_by_province:
            sel_region = route_str_to_region.get(sel_route_display, "")
            region_iatas = _route_region_airports.get(sel_region, set())
            df_route = ctx.df[
                ctx.df["origin"].isin(region_iatas)
                | ctx.df["destination"].isin(region_iatas)
            ]
        elif route_by_city:
            city_a, city_b = route_str_to_city_keys.get(
                sel_route_display, (("", ""), ("", ""))
            )
            _origin_city_keys = ctx.df["origin"].apply(_airport_city_key)
            _destination_city_keys = ctx.df["destination"].apply(_airport_city_key)
            mask_city_pair = (
                (_origin_city_keys == city_a) & (_destination_city_keys == city_b)
            ) | ((_origin_city_keys == city_b) & (_destination_city_keys == city_a))
            df_route = ctx.df[mask_city_pair]
        else:
            airport_a, airport_b = route_str_to_airports.get(
                sel_route_display, ("", "")
            )
            mask_both = (
                (ctx.df["origin"] == airport_a) & (ctx.df["destination"] == airport_b)
            ) | ((ctx.df["origin"] == airport_b) & (ctx.df["destination"] == airport_a))
            df_route = ctx.df[mask_both]

        if df_route.empty:
            st.info("No flights for this route in the selected filters.")
        else:
            render_route_tabs(
                ctx,
                df_route=df_route,
                route_by_country=route_by_country,
                route_by_province=route_by_province,
                route_by_city=route_by_city,
                sel_region=sel_region if route_by_country or route_by_province else "",
                city_a=city_a if route_by_city else None,
                city_b=city_b if route_by_city else None,
                airport_a=airport_a
                if not (route_by_country or route_by_province or route_by_city)
                else "",
                airport_b=airport_b
                if not (route_by_country or route_by_province or route_by_city)
                else "",
                _route_region_airports=_route_region_airports,
                _route_region_country=_route_region_country,
                _route_city_iatas=_route_city_iatas if route_by_city else {},
            )
