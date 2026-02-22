"""Airport lookup by IATA code."""

from dataclasses import dataclass
from importlib import resources
from typing import Optional

import json


@dataclass
class AirportInfo:
    """Airport details from reference data."""

    iata: str
    name: str
    city: str
    country: str
    latitude: float
    longitude: float


_airports_cache: Optional[dict[str, dict]] = None


def _load_airports() -> dict[str, dict]:
    global _airports_cache
    if _airports_cache is None:
        try:
            data_path = resources.files("flyghts.reference.data").joinpath("airports.json")
            with data_path.open() as f:
                _airports_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _airports_cache = {}
    return _airports_cache


def get_airport(iata: str) -> Optional[AirportInfo]:
    """Look up airport by IATA code. Returns None if not found."""
    if not iata:
        return None
    iata = iata.upper().strip()
    data = _load_airports()
    row = data.get(iata)
    if not row:
        return None
    return AirportInfo(
        iata=row.get("iata", iata),
        name=row.get("name", ""),
        city=row.get("city", ""),
        country=row.get("country", ""),
        latitude=float(row.get("latitude", 0)),
        longitude=float(row.get("longitude", 0)),
    )
