#!/usr/bin/env python3
"""
Download OpenFlights airport and airline data, parse to JSON, and save
into src/flyghts/reference/data/ for bundled package use.

Province/state names are enriched from OurAirports regions.csv.

Usage:
    uv run python scripts/fetch_reference_data.py
"""

import csv
import io
import json
from pathlib import Path

import requests

AIRPORTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
AIRLINES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
OURAIRPORTS_AIRPORTS_URL = (
    "https://davidmegginson.github.io/ourairports-data/airports.csv"
)
OURAIRPORTS_REGIONS_URL = (
    "https://davidmegginson.github.io/ourairports-data/regions.csv"
)


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


def main() -> None:
    data_dir = Path(__file__).resolve().parent.parent / "src" / "flyghts" / "reference" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

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
    print(f"Wrote {len(airports)} airports ({with_province} with province) to {airports_path}")

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
            entry: dict[str, str] = {
                "icao": icao,
                "name": row[1].strip() or "",
                "country": country,
            }
            if iata:
                entry["iata"] = iata.upper()
            airlines[icao] = entry
    airlines_path = data_dir / "airlines.json"
    with open(airlines_path, "w") as f:
        json.dump(airlines, f, indent=0)
    print(f"Wrote {len(airlines)} airlines to {airlines_path}")


if __name__ == "__main__":
    main()
