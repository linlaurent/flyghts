"""Label and route formatting helpers."""

from typing import Literal

import pandas as pd

from flyghts.reference import get_airline, get_airport

from .data import get_destination_column

RouteCityKey = tuple[str, str]


def _airline_label(code: str) -> str:
    info = get_airline(code)
    return f"{code} - {info.name}" if info and info.name else code


INDEPENDENT_ALLIANCE = "independent"

ALLIANCE_DISPLAY: dict[str, str] = {
    "oneworld": "oneworld",
    "skyteam": "SkyTeam",
    "star_alliance": "Star Alliance",
    INDEPENDENT_ALLIANCE: "Independent",
}

ALLIANCE_ORDER: list[str] = [
    "oneworld",
    "skyteam",
    "star_alliance",
    INDEPENDENT_ALLIANCE,
]


def _alliance_id(icao: str) -> str:
    """Map airline ICAO to OPTD alliance id (members only). Never from code-shares."""
    from flyghts.reference import get_alliance

    if not icao:
        return INDEPENDENT_ALLIANCE
    info = get_alliance(str(icao), members_only=True)
    if info is None:
        return INDEPENDENT_ALLIANCE
    return info.alliance


def _alliance_label(alliance_id: str) -> str:
    return ALLIANCE_DISPLAY.get(alliance_id, alliance_id)


def with_alliance_column(
    df: pd.DataFrame, airline_col: str, *, column: str = "alliance"
) -> pd.DataFrame:
    """Return a copy with OPTD alliance id per airline_col (members → independent)."""
    out = df.copy()
    if airline_col not in out.columns or out.empty:
        out[column] = INDEPENDENT_ALLIANCE
        return out
    codes = out[airline_col].astype(str)
    unique = codes.dropna().unique()
    mapping = {code: _alliance_id(code) for code in unique}
    out[column] = codes.map(mapping).fillna(INDEPENDENT_ALLIANCE)
    return out


def _route_label(origin: str, destination: str) -> str:
    o_info = get_airport(origin)
    d_info = get_airport(destination)
    o_label = f"{origin} ({o_info.city})" if o_info and o_info.city else origin
    d_label = (
        f"{destination} ({d_info.city})" if d_info and d_info.city else destination
    )
    return f"{o_label} → {d_label}"


def _airport_city_key(iata: str) -> RouteCityKey:
    info = get_airport(iata)
    if info and info.city:
        return (info.city, info.country or "")
    return (iata, "")


def _airport_province(iata: str) -> str:
    info = get_airport(iata)
    if info:
        province = getattr(info, "province", "")
        if province:
            return province
        if info.country:
            return info.country
    return iata


def _region_key_for_iata(iata: str, mode: Literal["country", "province"]) -> str:
    if mode == "province":
        return _airport_province(iata)
    info = get_airport(iata)
    return info.country if info and info.country else iata


def _build_region_route_selection(
    df: pd.DataFrame,
    direction: str,
    focus_airport: str | None,
    mode: Literal["country", "province"],
    *,
    multi_airport_only: bool,
) -> tuple[list[str], dict[str, str], dict[str, set[str]], dict[str, str]]:
    """Build region route list for country or province drill-down."""
    dest_codes = get_destination_column(df, direction, focus_airport)
    region_counts: dict[str, int] = {}
    region_airports: dict[str, set[str]] = {}
    region_country: dict[str, str] = {}

    for iata in pd.concat([df["origin"], df["destination"]]).dropna().unique():
        region = _region_key_for_iata(iata, mode)
        region_airports.setdefault(region, set()).add(iata)
        if mode == "province":
            info = get_airport(iata)
            if info and info.country:
                region_country.setdefault(region, info.country)

    for iata, count in dest_codes.value_counts().items():
        region = _region_key_for_iata(iata, mode)
        region_counts[region] = region_counts.get(region, 0) + count

    display_options: list[str] = []
    label_to_region: dict[str, str] = {}
    for region, count in sorted(region_counts.items(), key=lambda x: -x[1]):
        if multi_airport_only and len(region_airports.get(region, set())) < 2:
            continue
        if mode == "country":
            n_airports = len(region_airports.get(region, set()))
            region_name = f"{region} ({n_airports} airports)" if n_airports else region
        else:
            country = region_country.get(region, "")
            region_name = f"{region}, {country}" if country else region
        label = f"{region_name} - {count:,} flights"
        display_options.append(label)
        label_to_region[label] = region

    return display_options, label_to_region, region_airports, region_country


def _city_pair_airport_counts(
    df_route: pd.DataFrame, city_a: RouteCityKey, city_b: RouteCityKey
) -> pd.Series:
    """Count flights touching each airport in the selected city pair."""
    counts: dict[str, int] = {}
    city_keys = {city_a, city_b}
    for origin, destination in df_route[["origin", "destination"]].itertuples(
        index=False
    ):
        for iata in (origin, destination):
            if _airport_city_key(iata) in city_keys:
                counts[iata] = counts.get(iata, 0) + 1
    if not counts:
        return pd.Series(dtype=int)
    return pd.Series(counts).sort_values(ascending=False)


def _multi_airport_city_keys_for_iatas(iatas: set[str]) -> list[RouteCityKey]:
    """Return city keys that have multiple airports in the given IATA set."""
    city_iatas: dict[RouteCityKey, set[str]] = {}
    for iata in iatas:
        city_iatas.setdefault(_airport_city_key(iata), set()).add(iata)
    return [city_key for city_key, codes in city_iatas.items() if len(codes) >= 2]


def _city_key_label(city_key: RouteCityKey) -> str:
    city, country = city_key
    return f"{city}, {country}" if country else city


def _city_key_display(city_key: RouteCityKey, iatas: set[str] | None = None) -> str:
    label = _city_key_label(city_key)
    if not iatas:
        return label
    return f"{label} ({'/'.join(sorted(iatas))})"


def _format_insight_table(df: pd.DataFrame) -> pd.DataFrame:
    """Add readable labels and display-friendly column names for insight tables."""
    if df.empty:
        return df

    display = df.copy()
    if {"origin", "destination"}.issubset(display.columns):
        display.insert(
            0,
            "Route",
            display.apply(
                lambda r: _route_label(r["origin"], r["destination"]), axis=1
            ),
        )
    if "airline" in display.columns:
        display.insert(0, "Airline", display["airline"].apply(_airline_label))

    return display.rename(
        columns={
            "airline": "ICAO",
            "origin": "Origin",
            "destination": "Destination",
            "previous_flights": "Previous flights",
            "current_flights": "Current flights",
            "previous_flights_per_day": "Previous flights/day",
            "current_flights_per_day": "Current flights/day",
            "absolute_change_per_day": "Change/day",
            "percent_change": "Change (%)",
        }
    )
