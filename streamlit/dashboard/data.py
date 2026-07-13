"""Data loading and filtering for the flight dashboard."""

import re
from typing import Literal

import pandas as pd
import streamlit as st

from flyghts.reference import get_airport

from .config import DATASETS, PROJECT_ROOT

MapAggregateBy = Literal["airport", "province", "country"]

_DELAY_RE = re.compile(r"\(\+(\d+)min\)")


def load_flights(dataset_key: str) -> pd.DataFrame:
    """Load flight data for the given dataset (CSV or Parquet)."""
    dataset = DATASETS[dataset_key]
    data_dir = PROJECT_ROOT / "data" / dataset["dir"]
    file_format = dataset.get("format", "csv")

    if file_format == "parquet":
        files = sorted(data_dir.glob("*.parquet")) if data_dir.exists() else []
        if not files:
            st.error(
                f"No flight data found for {dataset_key}. Run the dump script first."
            )
            st.stop()
        dfs = [pd.read_parquet(f) for f in files]
    else:
        files = sorted(data_dir.glob("*.csv")) if data_dir.exists() else []
        if not files:
            st.error(
                f"No flight data found for {dataset_key}. Run the dump script first."
            )
            st.stop()
        dfs = [pd.read_csv(f) for f in files]

    df = pd.concat(dfs, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    if "cargo" in df.columns:

        def _to_bool(x):
            if pd.isna(x):
                return False
            if isinstance(x, bool):
                return x
            return str(x).lower() in ("true", "1", "yes")

        df["cargo"] = df["cargo"].apply(_to_bool)
    return df


def apply_filters(
    df: pd.DataFrame,
    direction: str,
    focus_airport: str | None,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    cargo_filter: str | None = None,
    operating_only: bool = False,
) -> pd.DataFrame:
    """Filter by direction relative to focus airport, date range, cargo, and operating-only.

    When focus_airport is None (global mode) no directional filter is applied.
    """
    mask = (df["date"] >= start_date) & (df["date"] <= end_date)
    if focus_airport:
        if direction == "Departures":
            mask = mask & (df["origin"] == focus_airport)
        elif direction == "Arrivals":
            mask = mask & (df["destination"] == focus_airport)
        else:
            mask = mask & (
                (df["origin"] == focus_airport) | (df["destination"] == focus_airport)
            )
    if cargo_filter and "cargo" in df.columns:
        if cargo_filter == "Passenger only":
            mask = mask & (~df["cargo"])
        elif cargo_filter == "Cargo only":
            mask = mask & df["cargo"]
    if operating_only and "operating_airline" in df.columns:
        mask = mask & (df["airline"] == df["operating_airline"])
    return df[mask]


def get_destination_column(
    df: pd.DataFrame, direction: str, focus_airport: str | None
) -> pd.Series:
    """Return the 'other end' airport codes relative to the focus airport.

    When focus_airport is None (global mode) returns the destination column directly.
    """
    if focus_airport is None:
        return df["destination"]
    if direction == "Departures":
        return df["destination"]
    if direction == "Arrivals":
        return df["origin"]
    origins = df[df["origin"] != focus_airport]["origin"]
    dests = df[df["destination"] != focus_airport]["destination"]
    return pd.concat([origins, dests])


def parse_delay_minutes(status: str) -> int | None:
    """Extract delay minutes from US-format status strings.

    Returns 0 for on-time arrivals, positive int for late arrivals,
    None for cancelled/diverted/unknown.
    """
    if not isinstance(status, str):
        return None
    s = status.strip()
    if s.startswith("Cancelled") or s.startswith("Diverted"):
        return None
    m = _DELAY_RE.search(s)
    if m:
        return int(m.group(1))
    if s.startswith("Arr ") or s.startswith("Dep "):
        return 0
    return None


def _map_region_key(iata: str, mode: Literal["province", "country"]) -> str:
    """Resolve province or country label for map aggregation."""
    info = get_airport(iata)
    if mode == "country":
        return info.country if info and info.country else iata
    if info:
        province = getattr(info, "province", "")
        if province:
            return province
        if info.country:
            return info.country
    return iata


def map_point_label_to_aggregate(map_point_by: str) -> MapAggregateBy:
    """Map UI radio label to build_map_points aggregate_by mode."""
    if map_point_by == "Country":
        return "country"
    if map_point_by == "Province":
        return "province"
    return "airport"


def build_map_points(
    dest_counts: "pd.Series",
    aggregate_by: MapAggregateBy = "airport",
) -> list[dict]:
    """Build map point data from destination IATA counts."""
    points: list[dict] = []
    if aggregate_by in ("province", "country"):
        region_agg: dict[str, list[tuple[float, float, int]]] = {}
        for iata, count in dest_counts.items():
            info = get_airport(iata)
            if not info or (info.latitude == 0 and info.longitude == 0):
                continue
            region = _map_region_key(iata, aggregate_by)
            region_agg.setdefault(region, []).append(
                (info.latitude, info.longitude, count)
            )
        for region, pts in region_agg.items():
            total = sum(p[2] for p in pts)
            if total == 0:
                continue
            lat = sum(p[0] * p[2] for p in pts) / total
            lon = sum(p[1] * p[2] for p in pts) / total
            points.append(
                {
                    "iata": region,
                    "lat": lat,
                    "lon": lon,
                    "count": total,
                    "label": f"{region}: {total:,} flights",
                }
            )
    else:
        for iata, count in dest_counts.items():
            info = get_airport(iata)
            if info and (info.latitude != 0 or info.longitude != 0):
                points.append(
                    {
                        "iata": iata,
                        "lat": info.latitude,
                        "lon": info.longitude,
                        "count": count,
                        "label": f"{iata} ({info.city or '?'}, {info.country or '?'}): {count:,}",
                    }
                )
    return points
