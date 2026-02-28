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
_iata_to_icao_cache: Optional[dict[str, str]] = None

# Manual overrides for airlines not in OpenFlights (preserved across fetch updates)
_AIRLINE_OVERRIDES: dict[str, dict] = {
    "AAE": {"icao": "AAE", "name": "Air Atlanta Europe", "country": "Malta"},
    "APZ": {"icao": "APZ", "name": "Air Premia", "country": "Republic of Korea"},
    "BTN": {"icao": "BTN", "name": "Bhutan Airlines", "country": "Bhutan"},
    "CDC": {"icao": "CDC", "name": "Zhejiang Loong Airlines", "country": "China"},
    "CSS": {"icao": "CSS", "name": "SF Airlines", "country": "China"},
    "EAU": {"icao": "EAU", "name": "Elitavia Malta", "country": "Malta"},
    "FKH": {"icao": "FKH", "name": "Fly Khiva", "country": "Uzbekistan"},
    "GEL": {"icao": "GEL", "name": "Geo-Sky", "country": "Georgia"},
    "HGB": {"icao": "HGB", "name": "Greater Bay Airlines", "country": "Hong Kong"},
    "HGO": {"icao": "HGO", "name": "One Air", "country": "United Kingdom"},
    "HKC": {"icao": "HKC", "name": "Hong Kong Air Cargo", "country": "Hong Kong"},
    "ICV": {"icao": "ICV", "name": "Cargolux Italia", "country": "Italy"},
    "IGT": {"icao": "IGT", "name": "Georgian Airlines", "country": "Georgia"},
    "KHV": {"icao": "KHV", "name": "Air Cambodia", "country": "Cambodia"},
    "LKH": {"icao": "LKH", "name": "Small Planet Airlines Cambodia", "country": "Cambodia"},
    "KME": {"icao": "KME", "name": "Cambodia Airways", "country": "Cambodia"},
    "KXP": {"icao": "KXP", "name": "MJets Air", "country": "Malaysia"},
    "LSI": {"icao": "LSI", "name": "MSC Air Cargo", "country": "Italy"},
    "MFX": {"icao": "MFX", "name": "My Freighter Airlines", "country": "Uzbekistan"},
    "MML": {"icao": "MML", "name": "Hunnu Air", "country": "Mongolia"},
    "MYU": {"icao": "MYU", "name": "My Indo Airlines", "country": "Indonesia"},
    "QDA": {"icao": "QDA", "name": "Qingdao Airlines", "country": "China"},
    "RCR": {"icao": "RCR", "name": "Romcargo Airlines", "country": "Romania"},
    "RMY": {"icao": "RMY", "name": "Raya Airways", "country": "Malaysia"},
    "SJX": {"icao": "SJX", "name": "Starlux Airlines", "country": "Taiwan"},
    "TGW": {"icao": "TGW", "name": "Scoot", "country": "Singapore"},
    "TMN": {"icao": "TMN", "name": "Tasman Cargo Airlines", "country": "Australia"},
    "UZU": {"icao": "UZU", "name": "SpaceBee Airlines", "country": "Uzbekistan"},
    "VYU": {"icao": "VYU", "name": "Vaayu", "country": "United Arab Emirates"},
    "WCM": {"icao": "WCM", "name": "World Cargo Airlines", "country": "Malaysia"},
    "WGN": {"icao": "WGN", "name": "Western Global Airlines", "country": "United States"},
    "XKY": {"icao": "XKY", "name": "Skyway Airlines", "country": "Philippines"},
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


def _build_iata_index() -> dict[str, str]:
    global _iata_to_icao_cache
    if _iata_to_icao_cache is None:
        data = _load_airlines()
        _iata_to_icao_cache = {}
        for icao_code, row in data.items():
            iata = row.get("iata", "")
            if iata and iata not in _iata_to_icao_cache:
                _iata_to_icao_cache[iata] = icao_code
    return _iata_to_icao_cache


def iata_to_icao(iata: str) -> Optional[str]:
    """Convert IATA 2-letter airline code to ICAO 3-letter code. Returns None if not found."""
    if not iata:
        return None
    iata = iata.upper().strip()
    return _build_iata_index().get(iata)


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


def get_airline_by_iata(iata: str) -> Optional[AirlineInfo]:
    """Look up airline by IATA 2-letter code. Returns None if not found."""
    icao = iata_to_icao(iata)
    if icao is None:
        return None
    return get_airline(icao)
