#!/usr/bin/env python3
"""
Download US domestic on-time flight performance data from the Bureau of
Transportation Statistics (BTS) and normalize to the project CSV format.

Data source: https://transtats.bts.gov/PREZIP/
  Direct ZIP downloads of "Marketing Carrier On-Time Performance" data.
  No API key required. Data is ~2-3 months behind current date.
  Coverage: all US domestic flights from carriers with >=0.5% market share.
  Available from January 2018 onwards.

Output columns: origin, destination, flight_no, airline, operating_flight_no,
operating_airline, scheduled_time, status, date, cargo.

Downloads monthly ZIPs but writes per-date CSV files (e.g. data/us/2025-11-01.csv)
to match the HKG and Korea data layout.

Usage:
    uv run python scripts/dump_us_flights.py --data-dir data/us/
    uv run python scripts/dump_us_flights.py --year 2024 --month 12 --data-dir data/us/
    uv run python scripts/dump_us_flights.py --year 2024 --start-month 10 --end-month 12 --data-dir data/us/
    uv run python scripts/dump_us_flights.py --latest --data-dir data/us/
"""

import argparse
import io
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

from flyghts.reference.airlines import iata_to_icao

PREZIP_URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Marketing_Carrier_On_Time_Performance"
    "_Beginning_January_2018_{year}_{month}.zip"
)


def _download_month(year: int, month: int, timeout: int = 180) -> pd.DataFrame:
    """Download one month of BTS on-time data and return as DataFrame."""
    url = PREZIP_URL.format(year=year, month=month)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    try:
        z = zipfile.ZipFile(io.BytesIO(resp.content))
    except zipfile.BadZipFile:
        raise RuntimeError(
            f"BTS returned non-ZIP response for {year}-{month:02d}. "
            f"Data may not be available yet. Size: {len(resp.content)} bytes"
        )

    csv_names = [n for n in z.namelist() if n.endswith(".csv")]
    if not csv_names:
        raise RuntimeError(f"No CSV file found in ZIP for {year}-{month:02d}")

    with z.open(csv_names[0]) as f:
        df = pd.read_csv(f, dtype=str, low_memory=False)

    return df


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize BTS DataFrame to project standard CSV format."""
    rows = []
    for _, r in df.iterrows():
        mkt_iata = str(r.get("IATA_Code_Marketing_Airline", "")).strip()
        mkt_icao = iata_to_icao(mkt_iata) or mkt_iata
        mkt_fl_num = str(r.get("Flight_Number_Marketing_Airline", "")).strip()
        flight_no = f"{mkt_iata} {mkt_fl_num}" if mkt_fl_num else mkt_iata

        op_iata = str(r.get("IATA_Code_Operating_Airline", "")).strip()
        op_icao = iata_to_icao(op_iata) or op_iata
        op_fl_num = str(r.get("Flight_Number_Operating_Airline", "")).strip()
        op_flight_no = f"{op_iata} {op_fl_num}" if op_fl_num else op_iata

        fl_date_str = str(r.get("FlightDate", "")).strip()
        try:
            fl_date = datetime.strptime(fl_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        crs_dep = str(r.get("CRSDepTime", "")).strip()
        scheduled_time = _parse_time(crs_dep, fl_date)

        status = _build_status(r)

        rows.append({
            "origin": str(r.get("Origin", "")).strip(),
            "destination": str(r.get("Dest", "")).strip(),
            "flight_no": flight_no,
            "airline": mkt_icao,
            "operating_flight_no": op_flight_no if op_iata else flight_no,
            "operating_airline": op_icao if op_iata else mkt_icao,
            "scheduled_time": scheduled_time,
            "status": status,
            "date": fl_date.isoformat(),
            "cargo": False,
        })

    if not rows:
        return pd.DataFrame(columns=[
            "origin", "destination", "flight_no", "airline",
            "operating_flight_no", "operating_airline",
            "scheduled_time", "status", "date", "cargo",
        ])
    return pd.DataFrame(rows)


def _parse_time(hhmm: str, fl_date: date) -> datetime | None:
    """Parse HHMM time string combined with flight date."""
    if not hhmm or hhmm in ("", "nan"):
        return None
    hhmm = hhmm.replace(".", "").zfill(4)
    try:
        h, m = int(hhmm[:2]), int(hhmm[2:4])
        if h == 24:
            h = 0
        return datetime(fl_date.year, fl_date.month, fl_date.day, h, m)
    except (ValueError, IndexError):
        return None


def _build_status(r: pd.Series) -> str:
    """Build a status string from BTS delay/cancellation fields."""
    cancelled = str(r.get("Cancelled", "0")).strip()
    if cancelled in ("1", "1.0", "1.00"):
        return "Cancelled"
    diverted = str(r.get("Diverted", "0")).strip()
    if diverted in ("1", "1.0", "1.00"):
        return "Diverted"

    arr_time = str(r.get("ArrTime", "")).strip()
    arr_delay = str(r.get("ArrDelay", "")).strip()

    if arr_delay and arr_delay not in ("", "nan"):
        try:
            delay_min = float(arr_delay)
            if delay_min <= 0:
                return f"Arr {arr_time.zfill(4)}" if arr_time and arr_time != "nan" else "On time"
            else:
                delay_str = f"+{int(delay_min)}min"
                return f"Arr {arr_time.zfill(4)} ({delay_str})" if arr_time and arr_time != "nan" else f"Delayed {delay_str}"
        except ValueError:
            pass

    dep_time = str(r.get("DepTime", "")).strip()
    if dep_time and dep_time not in ("", "nan"):
        return f"Dep {dep_time.zfill(4)}"
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download US domestic flight data from BTS"
    )
    parser.add_argument("--year", type=int, default=None, help="Year to download")
    parser.add_argument("--month", type=int, default=None, help="Single month (1-12)")
    parser.add_argument("--start-month", type=int, default=None, help="Start month for range")
    parser.add_argument("--end-month", type=int, default=None, help="End month for range")
    parser.add_argument(
        "--latest", action="store_true",
        help="Try to download the most recent available month (~2-3 months ago)",
    )
    parser.add_argument(
        "--data-dir", type=str, default=None,
        help="Output directory for per-month CSV files (e.g. data/us/)",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output single CSV file. Default: stdout",
    )
    args = parser.parse_args()

    if args.output and args.data_dir:
        print("Error: --output and --data-dir are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    today = date.today()

    if args.latest:
        target_month = today.month - 3
        target_year = today.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        months_to_fetch = [(target_year, target_month)]
    elif args.year and args.month:
        months_to_fetch = [(args.year, args.month)]
    elif args.year and args.start_month and args.end_month:
        months_to_fetch = [
            (args.year, m) for m in range(args.start_month, args.end_month + 1)
        ]
    elif args.year:
        max_month = 12
        if args.year == today.year:
            max_month = max(1, today.month - 3)
        months_to_fetch = [(args.year, m) for m in range(1, max_month + 1)]
    else:
        target_month = today.month - 3
        target_year = today.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        months_to_fetch = [(target_year, target_month)]

    all_dfs = []
    for year, month in tqdm(months_to_fetch, desc="Downloading BTS data", unit="month"):
        try:
            raw_df = _download_month(year, month)
            normalized = _normalize(raw_df)
            all_dfs.append((year, month, normalized))
            tqdm.write(
                f"  {year}-{month:02d}: {len(raw_df)} raw -> {len(normalized)} normalized",
                file=sys.stderr,
            )
        except Exception as e:
            tqdm.write(f"  Error downloading {year}-{month:02d}: {e}", file=sys.stderr)

    if not all_dfs:
        print("No data downloaded.", file=sys.stderr)
        sys.exit(1)

    if args.data_dir:
        data_dir = Path(args.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        combined = pd.concat([d for _, _, d in all_dfs], ignore_index=True)
        n_written = 0
        for date_str, group in combined.groupby("date"):
            group.to_csv(data_dir / f"{date_str}.csv", index=False)
            n_written += len(group)
        print(
            f"Wrote {n_written} flights across {combined['date'].nunique()} days to {data_dir}/",
            file=sys.stderr,
        )
    elif args.output:
        df = pd.concat([d for _, _, d in all_dfs], ignore_index=True)
        df.to_csv(args.output, index=False)
        print(f"Wrote {len(df)} flights to {args.output}", file=sys.stderr)
    else:
        df = pd.concat([d for _, _, d in all_dfs], ignore_index=True)
        print(df.to_csv(index=False))


if __name__ == "__main__":
    main()
