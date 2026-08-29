"""Unit tests for route deep dive drill-down helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

STREAMLIT_DIR = Path(__file__).resolve().parent.parent / "streamlit"
if str(STREAMLIT_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMLIT_DIR))

from dashboard.sections.route_dive.drilldown import (  # noqa: E402
    RouteDrillRequest,
    available_drill_levels,
    build_drill_request,
    city_pairs_for_city,
    collect_drill_entities,
    match_drill_to_route_label,
    resolve_airport_pair,
    resolve_city_pair,
)
from dashboard.formatting import _airport_city_key  # noqa: E402


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "origin": ["HKG", "HKG", "HKG", "ICN", "HKG"],
            "destination": ["ICN", "NRT", "ICN", "HKG", "LAX"],
        }
    )


def test_available_drill_levels() -> None:
    assert available_drill_levels("By country") == [
        "By province",
        "By city",
        "By airport",
    ]
    assert available_drill_levels("By province") == ["By city", "By airport"]
    assert available_drill_levels("By city") == ["By airport"]
    assert available_drill_levels("By airport") == []


def test_resolve_city_pair_prefers_highest_traffic() -> None:
    df = _sample_df()
    hkg_key = _airport_city_key("HKG")
    pair = resolve_city_pair(
        df,
        hkg_key,
        focus_airport=None,
        global_mode=True,
    )
    assert pair is not None
    assert hkg_key in pair
    icn_key = _airport_city_key("ICN")
    assert pair == tuple(sorted((hkg_key, icn_key)))


def test_city_pairs_for_city_lists_all_pairs() -> None:
    df = _sample_df()
    hkg_key = _airport_city_key("HKG")
    pairs = city_pairs_for_city(
        df,
        hkg_key,
        focus_airport=None,
        global_mode=True,
    )
    assert len(pairs) == 3
    assert pairs[0][2] >= pairs[1][2]


def test_resolve_airport_pair_with_focus_airport() -> None:
    df = _sample_df()
    pair = resolve_airport_pair(df, "ICN", focus_airport="HKG")
    assert pair == ("HKG", "ICN")


def test_resolve_airport_pair_global_mode() -> None:
    df = _sample_df()
    pair = resolve_airport_pair(df, "HKG", focus_airport=None)
    assert pair == ("HKG", "ICN")


def test_match_drill_to_route_label_for_region_city_and_airport() -> None:
    city_a = ("Hong Kong", "Hong Kong")
    city_b = ("Seoul", "South Korea")
    request_region = RouteDrillRequest(target_mode="By province", region="Guangdong")
    request_city = RouteDrillRequest(
        target_mode="By city",
        city_key=city_a,
        city_pair=(city_a, city_b),
    )
    request_airport = RouteDrillRequest(
        target_mode="By airport",
        airport_pair=("HKG", "ICN"),
    )

    assert (
        match_drill_to_route_label(
            request_region,
            route_str_to_region={"Guangdong, China - 100 flights": "Guangdong"},
            route_str_to_city_keys={},
            route_str_to_airports={},
        )
        == "Guangdong, China - 100 flights"
    )
    assert (
        match_drill_to_route_label(
            request_city,
            route_str_to_region={},
            route_str_to_city_keys={
                "Hong Kong ↔ Seoul — 50 flights": (city_a, city_b),
            },
            route_str_to_airports={},
        )
        == "Hong Kong ↔ Seoul — 50 flights"
    )
    assert (
        match_drill_to_route_label(
            request_airport,
            route_str_to_region={},
            route_str_to_city_keys={},
            route_str_to_airports={
                "HKG (Hong Kong) ↔ ICN (Seoul) — 10 flights": ("HKG", "ICN"),
            },
        )
        == "HKG (Hong Kong) ↔ ICN (Seoul) — 10 flights"
    )


def test_collect_drill_entities_for_airports() -> None:
    df = _sample_df()
    options = collect_drill_entities(df, "By airport")
    labels = [option.label for option in options]
    assert any(label.startswith("HKG -") for label in labels)
    assert any(label.startswith("ICN -") for label in labels)


def test_build_drill_request_for_city_and_airport() -> None:
    df = _sample_df()
    hkg_key = _airport_city_key("HKG")
    city_entities = collect_drill_entities(df, "By city")
    hkg_entity = next(entity for entity in city_entities if entity.city_key == hkg_key)
    city_request = build_drill_request(
        "By city",
        hkg_entity,
        df,
        focus_airport=None,
        global_mode=True,
    )
    assert city_request is not None
    assert city_request.target_mode == "By city"
    assert city_request.city_pair is not None

    airport_entities = collect_drill_entities(df, "By airport")
    icn_entity = next(entity for entity in airport_entities if entity.iata == "ICN")
    airport_request = build_drill_request(
        "By airport",
        icn_entity,
        df,
        focus_airport="HKG",
        global_mode=False,
    )
    assert airport_request is not None
    assert airport_request.airport_pair == ("HKG", "ICN")
