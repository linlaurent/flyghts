"""Airline lookup by ICAO code."""

from dataclasses import dataclass
from importlib import resources
from typing import Optional

import json


@dataclass
class AirlineInfo:
    """Airline details from reference data."""

    icao: str
    name: str
    country: str


_airlines_cache: Optional[dict[str, dict]] = None

# Manual overrides for airlines not in OpenFlights (preserved across fetch updates)
_AIRLINE_OVERRIDES: dict[str, dict] = {
    "HGB": {"icao": "HGB", "name": "Greater Bay Airlines", "country": "Hong Kong"},
}


def _load_airlines() -> dict[str, dict]:
    global _airlines_cache
    if _airlines_cache is None:
        try:
            data_path = resources.files("flyghts.reference.data").joinpath("airlines.json")
            with data_path.open() as f:
                _airlines_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _airlines_cache = {}
        _airlines_cache = {**_airlines_cache, **_AIRLINE_OVERRIDES}
    return _airlines_cache


def get_airline(icao: str) -> Optional[AirlineInfo]:
    """Look up airline by ICAO code. Returns None if not found."""
    if not icao:
        return None
    icao = icao.upper().strip()
    data = _load_airlines()
    row = data.get(icao)
    if not row:
        return None
    return AirlineInfo(
        icao=row.get("icao", icao),
        name=row.get("name", ""),
        country=row.get("country", ""),
    )
