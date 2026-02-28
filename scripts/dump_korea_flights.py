#!/usr/bin/env python3
"""
Dump all passenger flights from/to Incheon International Airport (ICN).

Output columns: origin, destination, flight_no, airline, operating_flight_no,
operating_airline, scheduled_time, status, date, cargo.

Requires KOREA_DATA_API_KEY environment variable (free key from data.go.kr).

The Korea passenger flight API provides current-day data only (no historical
date parameter). Run daily to accumulate data.

Output modes:
  --data-dir DIR  Write one CSV per date into DIR (e.g. data/korea/2026-02-28.csv).
  -o FILE         Write all flights to a single CSV, merging with existing data.
  (neither)       Print to stdout.

Usage:
    uv run python scripts/dump_korea_flights.py --data-dir data/korea/
    uv run python scripts/dump_korea_flights.py -o flights_korea.csv
    uv run python scripts/dump_korea_flights.py --debug
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

from flyghts.audit.sources.korea_airport import KoreaAirportSource

MAX_WORKERS = 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump all flights from/to Incheon (ICN)")
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output single CSV file (merges with existing). Default: stdout",
    )
    parser.add_argument(
        "--data-dir", type=str, default=None,
        help="Output directory for per-date CSV files (e.g. data/korea/)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Print raw API response structure and exit",
    )
    args = parser.parse_args()

    if args.output and args.data_dir:
        print("Error: --output and --data-dir are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    if args.debug:
        _debug_response()
        return

    source = KoreaAirportSource()
    today = date.today()

    jobs = [
        (False,),   # departures
        (True,),    # arrivals
    ]

    def fetch_one(job: tuple) -> list:
        arrival = job[0]
        return source.fetch_flights(today, arrival=arrival, cargo=False)

    all_raw = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_job = {executor.submit(fetch_one, job): job for job in jobs}
        for future in tqdm(
            as_completed(future_to_job), total=len(jobs),
            desc="Fetching ICN flights", unit="call",
        ):
            job = future_to_job[future]
            try:
                raw = future.result()
                all_raw.extend(raw)
            except Exception as e:
                tqdm.write(f"Error fetching arrival={job[0]}: {e}", file=sys.stderr)
                raise

    flights = [source.raw_to_flight(r) for r in all_raw]

    if args.data_dir:
        data_dir = Path(args.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        df = _to_dataframe(flights)
        date_str = today.isoformat()
        df.to_csv(data_dir / f"{date_str}.csv", index=False)
        print(f"Wrote {len(df)} flights to {data_dir}/{date_str}.csv", file=sys.stderr)
    elif args.output:
        new_df = _to_dataframe(flights)
        new_dates = set(new_df["date"].unique())
        existing_path = Path(args.output)
        if existing_path.exists():
            old_df = pd.read_csv(existing_path, dtype=str)
            kept_df = old_df[~old_df["date"].isin(new_dates)]
            df = pd.concat([kept_df, new_df], ignore_index=True)
        else:
            df = new_df
        df.to_csv(args.output, index=False)
        print(f"Wrote {len(df)} flights to {args.output}", file=sys.stderr)
    else:
        df = _to_dataframe(flights)
        print(df.to_csv(index=False))


def _debug_response() -> None:
    """Fetch and print raw API response structure for debugging."""
    import os
    api_key = os.environ.get("KOREA_DATA_API_KEY", "")
    if not api_key:
        print("Error: KOREA_DATA_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    from flyghts.audit.sources.korea_airport import ARRIVALS_ENDPOINT, DEPARTURES_ENDPOINT

    for endpoint, label in [
        (DEPARTURES_ENDPOINT, "DEPARTURES"),
        (ARRIVALS_ENDPOINT, "ARRIVALS"),
    ]:
        params = {
            "serviceKey": api_key,
            "type": "json",
            "numOfRows": "5",
            "pageNo": "1",
            "lang": "E",
        }
        resp = requests.get(endpoint, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print(f"\n=== {label} ===", file=sys.stderr)
        print(json.dumps(data, indent=2, default=str, ensure_ascii=False)[:3000], file=sys.stderr)


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
