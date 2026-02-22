#!/usr/bin/env python3
"""
Download OpenFlights airport and airline data, parse to JSON, and save
into src/flyghts/reference/data/ for bundled package use.

Usage:
    uv run python scripts/fetch_reference_data.py
"""

import csv
import json
from pathlib import Path

import requests

AIRPORTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
AIRLINES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"


def main() -> None:
    data_dir = Path(__file__).resolve().parent.parent / "src" / "flyghts" / "reference" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

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
            airports[iata] = {
                "iata": iata,
                "name": row[1].strip() or "",
                "city": row[2].strip() or "",
                "country": row[3].strip() or "",
                "latitude": lat,
                "longitude": lon,
            }
    airports_path = data_dir / "airports.json"
    with open(airports_path, "w") as f:
        json.dump(airports, f, indent=0)
    print(f"Wrote {len(airports)} airports to {airports_path}")

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
        country = row[6].strip() if len(row) > 6 else ""
        if icao not in airlines:
            airlines[icao] = {
                "icao": icao,
                "name": row[1].strip() or "",
                "country": country,
            }
    airlines_path = data_dir / "airlines.json"
    with open(airlines_path, "w") as f:
        json.dump(airlines, f, indent=0)
    print(f"Wrote {len(airlines)} airlines to {airlines_path}")


if __name__ == "__main__":
    main()
