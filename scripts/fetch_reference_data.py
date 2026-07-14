#!/usr/bin/env python3
"""
Download OpenFlights airport/airline data and OpenTravelData alliance
membership, parse to JSON, and save into src/flyghts/reference/data/
for bundled package use.

Province/state names are enriched from OurAirports regions.csv.

Alliance membership comes from OpenTravelData (CC-BY 4.0):
  https://github.com/opentraveldata/opentraveldata
Full membership intervals (from_date / to_date) are bundled for
point-in-time joins. OPTD can lag official alliance member lists;
spot-check when accuracy matters.

Usage:
    uv run python scripts/fetch_reference_data.py
    uv run python scripts/fetch_reference_data.py --alliances-only
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

import requests

AIRPORTS_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
)
AIRLINES_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
)
OURAIRPORTS_AIRPORTS_URL = (
    "https://davidmegginson.github.io/ourairports-data/airports.csv"
)
OURAIRPORTS_REGIONS_URL = (
    "https://davidmegginson.github.io/ourairports-data/regions.csv"
)
# OpenTravelData airline alliance membership (CC-BY 4.0)
ALLIANCES_URL = (
    "https://raw.githubusercontent.com/opentraveldata/opentraveldata/master/"
    "opentraveldata/optd_airline_alliance_membership.csv"
)

_ALLIANCE_NAME_MAP = {
    "oneworld": "oneworld",
    "skyteam": "skyteam",
    "star alliance": "star_alliance",
}


def _data_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "src"
        / "flyghts"
        / "reference"
        / "data"
    )


def _normalize_alliance(name: str) -> str | None:
    key = name.strip().lower()
    return _ALLIANCE_NAME_MAP.get(key)


def _normalize_alliance_type(raw: str) -> str:
    value = raw.strip().lower()
    if value == "affiliate":
        return "affiliate"
    return "member"


def _iata_to_icao_from_airlines(airlines_path: Path) -> dict[str, str]:
    """Build IATA -> ICAO from bundled airlines.json when present."""
    if not airlines_path.is_file():
        return {}
    with open(airlines_path) as f:
        airlines = json.load(f)
    index: dict[str, str] = {}
    for icao, row in airlines.items():
        iata = (row.get("iata") or "").strip().upper()
        if iata and iata not in index:
            index[iata] = icao
    return index


def _load_ourairports_provinces() -> dict[str, str]:
    """Build IATA -> admin region name from OurAirports airports + regions."""
    print("Fetching OurAirports regions.csv...")
    regions_resp = requests.get(OURAIRPORTS_REGIONS_URL, timeout=60)
    regions_resp.raise_for_status()
    region_names: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(regions_resp.text)):
        code = (row.get("code") or "").strip()
        name = (row.get("name") or "").strip()
        if code and name:
            region_names[code] = name

    print("Fetching OurAirports airports.csv...")
    airports_resp = requests.get(OURAIRPORTS_AIRPORTS_URL, timeout=60)
    airports_resp.raise_for_status()
    iata_to_province: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(airports_resp.text)):
        iata = (row.get("iata_code") or "").strip()
        iso_region = (row.get("iso_region") or "").strip()
        if not iata or not iso_region:
            continue
        province = region_names.get(iso_region, "")
        if province:
            iata_to_province[iata] = province
    print(f"Resolved province for {len(iata_to_province)} IATA codes")
    return iata_to_province


def fetch_airports_and_airlines(data_dir: Path) -> None:
    iata_to_province = _load_ourairports_provinces()

    # Fetch and parse airports
    print("Fetching airports.dat...")
    resp = requests.get(AIRPORTS_URL, timeout=30)
    resp.raise_for_status()
    airports: dict[str, dict] = {}
    reader = csv.reader(resp.text.strip().splitlines())
    for row in reader:
        if len(row) < 10:
            continue
        # ID, Name, City, Country, IATA, ICAO, Lat, Lon, Alt, TZ, DST, TZ_name, Type, Source
        iata = row[4].strip() if len(row) > 4 else ""
        if not iata or iata == "\\N":
            continue
        try:
            lat = float(row[6])
            lon = float(row[7])
        except (ValueError, IndexError):
            continue
        # Prefer first occurrence for duplicates (often primary airport)
        if iata not in airports:
            entry: dict[str, str | float] = {
                "iata": iata,
                "name": row[1].strip() or "",
                "city": row[2].strip() or "",
                "country": row[3].strip() or "",
                "latitude": lat,
                "longitude": lon,
            }
            province = iata_to_province.get(iata)
            if province:
                entry["province"] = province
            airports[iata] = entry
    airports_path = data_dir / "airports.json"
    with open(airports_path, "w") as f:
        json.dump(airports, f, indent=0)
    with_province = sum(1 for a in airports.values() if a.get("province"))
    print(
        f"Wrote {len(airports)} airports ({with_province} with province) to {airports_path}"
    )

    # Fetch and parse airlines
    print("Fetching airlines.dat...")
    resp = requests.get(AIRLINES_URL, timeout=30)
    resp.raise_for_status()
    airlines: dict[str, dict] = {}
    reader = csv.reader(resp.text.strip().splitlines())
    for row in reader:
        if len(row) < 8:
            continue
        # ID, Name, Alias, IATA, ICAO, Callsign, Country, Active
        icao = row[4].strip() if len(row) > 4 else ""
        if not icao or icao == "\\N" or icao.upper() == "N/A":
            continue
        icao = icao.upper()
        iata = row[3].strip() if len(row) > 3 else ""
        if iata == "\\N" or iata.upper() == "N/A":
            iata = ""
        country = row[6].strip() if len(row) > 6 else ""
        if icao not in airlines:
            airline_entry: dict[str, str] = {
                "icao": icao,
                "name": row[1].strip() or "",
                "country": country,
            }
            if iata:
                airline_entry["iata"] = iata.upper()
            airlines[icao] = airline_entry
    airlines_path = data_dir / "airlines.json"
    with open(airlines_path, "w") as f:
        json.dump(airlines, f, indent=0)
    print(f"Wrote {len(airlines)} airlines to {airlines_path}")


def fetch_alliances(data_dir: Path) -> None:
    """Download OPTD alliance membership and write alliances.json (intervals)."""
    print("Fetching OPTD alliance membership...")
    resp = requests.get(ALLIANCES_URL, timeout=60)
    resp.raise_for_status()

    iata_to_icao = _iata_to_icao_from_airlines(data_dir / "airlines.json")
    by_iata: dict[str, list[dict]] = {}
    reader = csv.DictReader(io.StringIO(resp.text), delimiter="^")
    for row in reader:
        iata = (row.get("airline_iata_code_2c") or "").strip().upper()
        if not iata:
            continue
        alliance = _normalize_alliance(row.get("alliance_name") or "")
        if alliance is None:
            continue
        alliance_type = _normalize_alliance_type(row.get("alliance_type") or "")
        name = (row.get("airline_name") or "").strip()
        from_raw = (row.get("from_date") or "").strip()
        to_raw = (row.get("to_date") or "").strip()
        entry: dict = {
            "iata": iata,
            "name": name,
            "alliance": alliance,
            "alliance_type": alliance_type,
            "from_date": from_raw or None,
            "to_date": to_raw or None,
        }
        icao = iata_to_icao.get(iata)
        if icao:
            entry["icao"] = icao
        by_iata.setdefault(iata, []).append(entry)

    by_icao: dict[str, list[dict]] = {}
    for intervals in by_iata.values():
        for entry in intervals:
            icao = entry.get("icao")
            if not icao:
                continue
            by_icao.setdefault(icao, []).append(entry)

    n_intervals = sum(len(v) for v in by_iata.values())
    n_open = sum(
        1 for intervals in by_iata.values() for e in intervals if not e.get("to_date")
    )
    payload = {
        "source": "OpenTravelData optd_airline_alliance_membership.csv",
        "license": "CC-BY-4.0",
        "note": (
            "Point-in-time intervals (from_date/to_date). "
            "OPTD can lag official alliance lists."
        ),
        "by_iata": by_iata,
        "by_icao": by_icao,
    }
    alliances_path = data_dir / "alliances.json"
    with open(alliances_path, "w") as f:
        json.dump(payload, f, indent=0)
    print(
        f"Wrote {n_intervals} alliance intervals "
        f"({n_open} open-ended, {len(by_icao)} ICAO keys) to {alliances_path}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch bundled airport, airline, and alliance reference data."
    )
    parser.add_argument(
        "--alliances-only",
        action="store_true",
        help="Only refresh alliances.json from OpenTravelData (skip OpenFlights).",
    )
    args = parser.parse_args()

    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    if not args.alliances_only:
        fetch_airports_and_airlines(data_dir)
    fetch_alliances(data_dir)


if __name__ == "__main__":
    main()
