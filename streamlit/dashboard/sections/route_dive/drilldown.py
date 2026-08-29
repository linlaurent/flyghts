"""Hierarchical drill-down helpers for route deep dive."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd
import streamlit as st
from flyghts.reference import get_airport

from ...formatting import (
    RouteCityKey,
    _airport_city_key,
    _airport_province,
    _city_key_display,
    _city_key_label,
)

RouteMode = Literal["By country", "By province", "By city", "By airport"]
DrillTargetMode = Literal["By province", "By city", "By airport"]

_DRILL_REQUEST_KEY = "route_dive_drill_request"
_PENDING_DRILL_KEY = "route_dive_pending_drill"

_DRILL_LEVELS: dict[RouteMode, list[DrillTargetMode]] = {
    "By country": ["By province", "By city", "By airport"],
    "By province": ["By city", "By airport"],
    "By city": ["By airport"],
    "By airport": [],
}


@dataclass(frozen=True)
class RouteDrillRequest:
    target_mode: DrillTargetMode
    region: str | None = None
    city_key: RouteCityKey | None = None
    city_pair: tuple[RouteCityKey, RouteCityKey] | None = None
    airport_pair: tuple[str, str] | None = None


@dataclass(frozen=True)
class DrillEntityOption:
    label: str
    region: str | None = None
    city_key: RouteCityKey | None = None
    iata: str | None = None


def available_drill_levels(current_mode: RouteMode) -> list[DrillTargetMode]:
    return list(_DRILL_LEVELS.get(current_mode, []))


def current_level_caption(
    *,
    route_by_country: bool,
    route_by_province: bool,
    route_by_city: bool,
    route_label: str,
) -> str:
    if route_by_country:
        level = "country"
    elif route_by_province:
        level = "province"
    elif route_by_city:
        level = "city"
    else:
        level = "airport"
    return f"Viewing at {level} level: {route_label}"


def _iatas_in_route(df_route: pd.DataFrame) -> set[str]:
    return set(
        pd.concat([df_route["origin"], df_route["destination"]]).dropna().unique()
    )


def collect_drill_entities(
    df_route: pd.DataFrame,
    target_mode: DrillTargetMode,
) -> list[DrillEntityOption]:
    iatas = _iatas_in_route(df_route)
    options: list[DrillEntityOption] = []

    if target_mode == "By province":
        province_counts: dict[str, int] = {}
        province_country: dict[str, str] = {}
        for iata in iatas:
            province = _airport_province(iata)
            province_counts[province] = province_counts.get(province, 0) + 1
            info = get_airport(iata)
            if info and info.country:
                province_country.setdefault(province, info.country)
        for province, count in sorted(
            province_counts.items(), key=lambda x: (-x[1], x[0])
        ):
            country = province_country.get(province, "")
            label = f"{province}, {country}" if country else province
            label = f"{label} — {count:,} flights"
            options.append(DrillEntityOption(label=label, region=province))
    elif target_mode == "By city":
        city_counts: dict[RouteCityKey, int] = {}
        city_iatas: dict[RouteCityKey, set[str]] = {}
        for iata in iatas:
            city_key = _airport_city_key(iata)
            city_counts[city_key] = city_counts.get(city_key, 0) + 1
            city_iatas.setdefault(city_key, set()).add(iata)
        for city_key, count in sorted(
            city_counts.items(), key=lambda x: (-x[1], x[0][0])
        ):
            label = (
                f"{_city_key_display(city_key, city_iatas.get(city_key))}"
                f" — {count:,} flights"
            )
            options.append(DrillEntityOption(label=label, city_key=city_key))
    else:
        airport_counts: dict[str, int] = {}
        for origin, destination in df_route[["origin", "destination"]].itertuples(
            index=False
        ):
            for iata in (origin, destination):
                if iata in iatas:
                    airport_counts[iata] = airport_counts.get(iata, 0) + 1
        for iata, count in sorted(airport_counts.items(), key=lambda x: (-x[1], x[0])):
            info = get_airport(iata)
            name = info.name if info and info.name else iata
            label = f"{iata} - {name} — {count:,} flights"
            options.append(DrillEntityOption(label=label, iata=iata))

    return options


def _city_pair_counts(
    df: pd.DataFrame,
) -> dict[tuple[RouteCityKey, RouteCityKey], int]:
    counts: dict[tuple[RouteCityKey, RouteCityKey], int] = {}
    for origin, destination in df[["origin", "destination"]].itertuples(index=False):
        city_pair = tuple(
            sorted((_airport_city_key(origin), _airport_city_key(destination)))
        )
        counts[city_pair] = counts.get(city_pair, 0) + 1
    return counts


def city_pairs_for_city(
    df: pd.DataFrame,
    city_key: RouteCityKey,
    *,
    focus_airport: str | None,
    global_mode: bool,
) -> list[tuple[str, tuple[RouteCityKey, RouteCityKey], int]]:
    """Return city pairs involving city_key as (label, pair, count) sorted by count."""
    focus_city_key = _airport_city_key(focus_airport) if focus_airport else None
    city_iatas: dict[RouteCityKey, set[str]] = {}
    for origin, destination in df[["origin", "destination"]].itertuples(index=False):
        for iata in (origin, destination):
            city_iatas.setdefault(_airport_city_key(iata), set()).add(iata)

    pairs: list[tuple[str, tuple[RouteCityKey, RouteCityKey], int]] = []
    for (city_a, city_b), count in sorted(
        _city_pair_counts(df).items(), key=lambda x: -x[1]
    ):
        if city_key not in (city_a, city_b):
            continue
        if global_mode or not focus_city_key:
            label = (
                f"{_city_key_display(city_a, city_iatas.get(city_a))}"
                f" ↔ {_city_key_display(city_b, city_iatas.get(city_b))}"
                f" — {count:,} flights"
            )
        elif city_a == focus_city_key or city_b == focus_city_key:
            other_city = city_b if city_a == focus_city_key else city_a
            label = (
                f"{_city_key_display(other_city, city_iatas.get(other_city))}"
                f" — {count:,} flights"
            )
        else:
            label = (
                f"{_city_key_display(city_a, city_iatas.get(city_a))}"
                f" ↔ {_city_key_display(city_b, city_iatas.get(city_b))}"
                f" — {count:,} flights"
            )
        pairs.append((label, (city_a, city_b), count))
    return pairs


def resolve_city_pair(
    df: pd.DataFrame,
    city_key: RouteCityKey,
    *,
    focus_airport: str | None,
    global_mode: bool,
) -> tuple[RouteCityKey, RouteCityKey] | None:
    pairs = city_pairs_for_city(
        df, city_key, focus_airport=focus_airport, global_mode=global_mode
    )
    if not pairs:
        return None
    return pairs[0][1]


def resolve_airport_pair(
    df: pd.DataFrame,
    iata: str,
    *,
    focus_airport: str | None,
) -> tuple[str, str] | None:
    if focus_airport and focus_airport != iata:
        return tuple(sorted((focus_airport, iata)))

    partner_counts: dict[str, int] = {}
    for origin, destination in df[["origin", "destination"]].itertuples(index=False):
        if origin == iata and destination != iata:
            partner_counts[destination] = partner_counts.get(destination, 0) + 1
        elif destination == iata and origin != iata:
            partner_counts[origin] = partner_counts.get(origin, 0) + 1

    if not partner_counts:
        return None
    top_partner = max(partner_counts.items(), key=lambda x: (x[1], x[0]))[0]
    return tuple(sorted((iata, top_partner)))


def build_drill_request(
    target_mode: DrillTargetMode,
    entity: DrillEntityOption,
    df_route: pd.DataFrame,
    *,
    focus_airport: str | None,
    global_mode: bool,
    city_pair: tuple[RouteCityKey, RouteCityKey] | None = None,
) -> RouteDrillRequest | None:
    if target_mode == "By province":
        if not entity.region:
            return None
        return RouteDrillRequest(target_mode="By province", region=entity.region)

    if target_mode == "By city":
        if not entity.city_key:
            return None
        pair = city_pair or resolve_city_pair(
            df_route,
            entity.city_key,
            focus_airport=focus_airport,
            global_mode=global_mode,
        )
        if pair is None:
            return None
        return RouteDrillRequest(
            target_mode="By city",
            city_key=entity.city_key,
            city_pair=pair,
        )

    if not entity.iata:
        return None
    pair = resolve_airport_pair(df_route, entity.iata, focus_airport=focus_airport)
    if pair is None:
        return None
    return RouteDrillRequest(
        target_mode="By airport",
        airport_pair=pair,
    )


def match_drill_to_route_label(
    request: RouteDrillRequest,
    *,
    route_str_to_region: dict[str, str],
    route_str_to_city_keys: dict[str, tuple[RouteCityKey, RouteCityKey]],
    route_str_to_airports: dict[str, tuple[str, str]],
) -> str | None:
    if request.target_mode == "By province" and request.region:
        for label, region in route_str_to_region.items():
            if region == request.region:
                return label

    if request.target_mode == "By city" and request.city_pair:
        city_a, city_b = request.city_pair
        for label, pair in route_str_to_city_keys.items():
            if pair == (city_a, city_b):
                return label

    if request.target_mode == "By airport" and request.airport_pair:
        airport_a, airport_b = request.airport_pair
        for label, pair in route_str_to_airports.items():
            if pair == (airport_a, airport_b):
                return label

    return None


def apply_drill_request(request: RouteDrillRequest) -> None:
    st.session_state[_DRILL_REQUEST_KEY] = request


def consume_drill_request() -> RouteDrillRequest | None:
    request = st.session_state.pop(_DRILL_REQUEST_KEY, None)
    if request is None:
        return None
    st.session_state["route_dive_by"] = request.target_mode
    st.session_state[f"route_dive_multi_airport_only_{request.target_mode}"] = False
    st.session_state[_PENDING_DRILL_KEY] = request
    return request


def consume_pending_drill_match(
    *,
    route_str_to_region: dict[str, str],
    route_str_to_city_keys: dict[str, tuple[RouteCityKey, RouteCityKey]],
    route_str_to_airports: dict[str, tuple[str, str]],
) -> str | None:
    request = st.session_state.pop(_PENDING_DRILL_KEY, None)
    if request is None:
        return None
    return match_drill_to_route_label(
        request,
        route_str_to_region=route_str_to_region,
        route_str_to_city_keys=route_str_to_city_keys,
        route_str_to_airports=route_str_to_airports,
    )
