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

# Manual overrides for airports not in OpenFlights (preserved across fetch updates)
_AIRPORT_OVERRIDES: dict[str, dict] = {
    "BSZ": {
        "iata": "BSZ",
        "name": "Manas International Airport",
        "city": "Bishkek",
        "country": "Kyrgyzstan",
        "latitude": 43.0613,
        "longitude": 74.4776,
    },
    "EAR": {
        "iata": "EAR",
        "name": "Kearney Regional Airport",
        "city": "Kearney",
        "country": "United States",
        "latitude": 40.727,
        "longitude": -99.0068,
    },
    "EHU": {
        "iata": "EHU",
        "name": "Ezhou Huahu International Airport",
        "city": "Ezhou",
        "country": "China",
        "latitude": 30.3483,
        "longitude": 114.9625,
    },
    "HSA": {
        "iata": "HSA",
        "name": "Hazret Sultan International Airport",
        "city": "Turkistan",
        "country": "Kazakhstan",
        "latitude": 43.311,
        "longitude": 68.55,
    },
    "INC": {
        "iata": "INC",
        "name": "Yinchuan Hedong International Airport",
        "city": "Yinchuan",
        "country": "China",
        "latitude": 38.3217,
        "longitude": 106.3925,
    },
    "NLU": {
        "iata": "NLU",
        "name": "Felipe Ángeles International Airport",
        "city": "Zumpango",
        "country": "Mexico",
        "latitude": 19.7567,
        "longitude": -99.0153,
    },
    "TFU": {
        "iata": "TFU",
        "name": "Chengdu Tianfu International Airport",
        "city": "Chengdu",
        "country": "China",
        "latitude": 30.323,
        "longitude": 104.445,
    },
    "UBN": {
        "iata": "UBN",
        "name": "Chinggis Khaan International Airport",
        "city": "Ulaanbaatar",
        "country": "Mongolia",
        "latitude": 47.647,
        "longitude": 106.82,
    },
    "XWA": {
        "iata": "XWA",
        "name": "Williston Basin International Airport",
        "city": "Williston",
        "country": "United States",
        "latitude": 48.2608,
        "longitude": -103.7508,
    },
}


def _load_airports() -> dict[str, dict]:
    global _airports_cache
    if _airports_cache is None:
        try:
            data_path = resources.files("flyghts.reference.data").joinpath("airports.json")
            with data_path.open() as f:
                _airports_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _airports_cache = {}
        _airports_cache = {**_airports_cache, **_AIRPORT_OVERRIDES}
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
