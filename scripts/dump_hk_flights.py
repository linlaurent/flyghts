#!/usr/bin/env python3
"""
Dump all flights from or to Hong Kong for a given date or date range.

Output columns: origin, destination, flight_no, airline, operating_flight_no,
operating_airline, scheduled_time, status, date, cargo. Cargo flights included by default.

Usage:
    uv run python scripts/dump_hk_flights.py
    uv run python scripts/dump_hk_flights.py --date 2025-02-17
    uv run python scripts/dump_hk_flights.py --start 2026-01-01 --end 2026-02-20 -o flights.csv
    uv run python scripts/dump_hk_flights.py --no-cargo -o flights.csv   # passenger only
    uv run python scripts/dump_hk_flights.py --deduplicate -o flights.csv  # one row per physical flight
    uv run python scripts/dump_hk_flights.py --debug  # inspect raw API response
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd
import requests
from tqdm import tqdm

from flyghts.audit.sources.hk_airport import HKAirportSource

API_URL = "https://www.hongkongairport.com/flightinfo-rest/rest/flights/past"
MAX_WORKERS = 3


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump all flights from/to HK")
    parser.add_argument(
        "--date",
        "-d",
        type=str,
        default=None,
        help="Single date (YYYY-MM-DD). Default: yesterday",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date for range (YYYY-MM-DD). Use with --end",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date for range (YYYY-MM-DD). Use with --start",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output CSV file. Default: stdout",
    )
    parser.add_argument(
        "--no-cargo",
        action="store_true",
        help="Exclude cargo flights (default: include both passenger and cargo)",
    )
    parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Keep only operating carrier rows (one per physical flight; drops code-share duplicates)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print raw API response structure and exit",
    )
    args = parser.parse_args()

    if args.start and args.end:
        try:
            start_date = date.fromisoformat(args.start)
            end_date = date.fromisoformat(args.end)
        except ValueError as e:
            print(f"Error: Invalid date - {e}", file=sys.stderr)
            sys.exit(1)
        if start_date > end_date:
            print("Error: --start must be before or equal to --end", file=sys.stderr)
            sys.exit(1)
        date_range = _date_range(start_date, end_date)
    elif args.date:
        try:
            flight_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"Error: Invalid date {args.date}", file=sys.stderr)
            sys.exit(1)
        date_range = [flight_date]
    else:
        flight_date = date.today() - timedelta(days=1)
        date_range = [flight_date]

    if args.debug:
        _debug_response(date_range[0], cargo=not args.no_cargo)
        return

    include_cargo = not args.no_cargo
    source = HKAirportSource()

    # Build list of fetch jobs: (sort_key, date, arrival, cargo)
    jobs = []
    for i, d in enumerate(date_range):
        if include_cargo:
            jobs.append((i, d, False, False))
            jobs.append((i, d, True, False))
            jobs.append((i, d, False, True))
            jobs.append((i, d, True, True))
        else:
            jobs.append((i, d, False, False))
            jobs.append((i, d, True, False))

    def fetch_one(job: tuple) -> tuple:
        sort_key, d, arrival, cargo = job
        raw = source.fetch_flights(d, arrival=arrival, cargo=cargo)
        return (sort_key, arrival, cargo, raw)

    results_by_key: dict[tuple, list] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_job = {executor.submit(fetch_one, job): job for job in jobs}
        for future in tqdm(
            as_completed(future_to_job),
            total=len(jobs),
            desc="Fetching flights",
            unit="call",
        ):
            job = future_to_job[future]
            sort_key, d, arrival, cargo = job[0], job[1], job[2], job[3]
            try:
                _, arrival, cargo, raw = future.result()
                results_by_key[(sort_key, arrival, cargo)] = raw
            except Exception as e:
                tqdm.write(
                    f"Error fetching {d} arrival={arrival} cargo={cargo}: {e}",
                    file=sys.stderr,
                )
                raise

    # Reassemble in original order (by date, then dep/arr pax, dep/arr cargo)
    all_raw = []
    for i in range(len(date_range)):
        if include_cargo:
            all_raw.extend(results_by_key.get((i, False, False), []))
            all_raw.extend(results_by_key.get((i, True, False), []))
            all_raw.extend(results_by_key.get((i, False, True), []))
            all_raw.extend(results_by_key.get((i, True, True), []))
        else:
            all_raw.extend(results_by_key.get((i, False, False), []))
            all_raw.extend(results_by_key.get((i, True, False), []))

    flights = [source.raw_to_flight(r) for r in all_raw]

    if args.deduplicate:
        flights = [f for f in flights if f.operating_airline and f.airline == f.operating_airline]

    if args.output:
        df = _to_dataframe(flights)
        df.to_csv(args.output, index=False)
        print(f"Wrote {len(flights)} flights ({len(date_range)} days) to {args.output}", file=sys.stderr)
    else:
        df = _to_dataframe(flights)
        print(df.to_csv(index=False))


def _date_range(start: date, end: date) -> list:
    """Return list of dates from start to end (inclusive)."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _debug_response(flight_date: date, cargo: bool) -> None:
    """Fetch and print raw API response structure for debugging."""
    for arrival, label in [(False, "departures"), (True, "arrivals")]:
        params = {
            "date": flight_date.strftime("%Y-%m-%d"),
            "arrival": str(arrival).lower(),
            "cargo": str(cargo).lower(),
            "lang": "en",
        }
        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print(f"\n=== {label.upper()} (arrival={arrival}) ===", file=sys.stderr)
        print(f"Response type: {type(data).__name__}", file=sys.stderr)
        if isinstance(data, list):
            flight_list = data
            print(f"List length: {len(flight_list)}", file=sys.stderr)
            if flight_list:
                print("First item keys:", list(flight_list[0].keys()) if isinstance(flight_list[0], dict) else "N/A", file=sys.stderr)
                print("First item sample:", json.dumps(flight_list[0], indent=2, default=str)[:2000], file=sys.stderr)
        else:
            flight_list = data.get("List") or data.get("list") or []
            print(f"Top-level keys: {list(data.keys())}", file=sys.stderr)
            print(f"List length: {len(flight_list)}", file=sys.stderr)
            if flight_list:
                print("First item keys:", list(flight_list[0].keys()) if isinstance(flight_list[0], dict) else "N/A", file=sys.stderr)
                print("First item sample:", json.dumps(flight_list[0], indent=2, default=str)[:2000], file=sys.stderr)


def _to_dataframe(flights: list) -> pd.DataFrame:
    if not flights:
        return pd.DataFrame(
            columns=[
                "origin", "destination", "flight_no", "airline",
                "operating_flight_no", "operating_airline",
                "scheduled_time", "status", "date", "cargo",
            ]
        )
    return pd.DataFrame(
        [
            {
                "origin": f.origin,
                "destination": f.destination,
                "flight_no": f.flight_no,
                "airline": f.airline,
                "operating_flight_no": f.operating_flight_no,
                "operating_airline": f.operating_airline,
                "scheduled_time": f.scheduled_time,
                "status": f.status,
                "date": f.date.isoformat(),
                "cargo": f.cargo if f.cargo is not None else False,
            }
            for f in flights
        ]
    )


if __name__ == "__main__":
    main()
