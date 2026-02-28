#!/usr/bin/env python3
"""
Validate flight CSVs against reference data (airlines.json / airports.json).

Scans flight CSV files and reports airline codes and airport codes that are
not found in the reference data, sorted by frequency. Helps identify which
entries need to be added to _AIRLINE_OVERRIDES / _AIRPORT_OVERRIDES.

Usage:
    uv run python scripts/validate_reference_data.py                        # all sources
    uv run python scripts/validate_reference_data.py --data-dir data/korea/
    uv run python scripts/validate_reference_data.py --data-dir data/us/
    uv run python scripts/validate_reference_data.py --data-dir data/hkg/
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from flyghts.reference.airlines import get_airline
from flyghts.reference.airports import get_airport

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


def _load_all_csvs(data_dir: Path) -> pd.DataFrame:
    """Load all CSV files from a directory (recursively)."""
    csv_files = sorted(data_dir.rglob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {data_dir}", file=sys.stderr)
        sys.exit(1)
    dfs = [pd.read_csv(f, dtype=str) for f in csv_files]
    df = pd.concat(dfs, ignore_index=True)
    print(f"Loaded {len(df)} rows from {len(csv_files)} files in {data_dir}", file=sys.stderr)
    return df


def _validate_airlines(df: pd.DataFrame) -> list[tuple[str, int]]:
    """Find airline codes not in reference data. Returns (code, count) pairs."""
    codes: Counter[str] = Counter()

    for col in ("airline", "operating_airline"):
        if col not in df.columns:
            continue
        for val in df[col].dropna():
            code = str(val).strip()
            if code:
                codes[code] += 1

    missing = []
    for code, count in codes.most_common():
        if not get_airline(code):
            missing.append((code, count))
    return missing


def _validate_airports(df: pd.DataFrame) -> list[tuple[str, int]]:
    """Find airport codes not in reference data. Returns (code, count) pairs."""
    codes: Counter[str] = Counter()

    for col in ("origin", "destination"):
        if col not in df.columns:
            continue
        for val in df[col].dropna():
            code = str(val).strip()
            if code:
                codes[code] += 1

    missing = []
    for code, count in codes.most_common():
        if not get_airport(code):
            missing.append((code, count))
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate flight CSVs against reference data"
    )
    parser.add_argument(
        "--data-dir", type=str, default=None,
        help="Directory to scan (default: data/ with all subdirectories)",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_DATA_DIR
    df = _load_all_csvs(data_dir)

    missing_airlines = _validate_airlines(df)
    missing_airports = _validate_airports(df)

    total_airline_codes = len(
        set(df["airline"].dropna().unique())
        | (set(df["operating_airline"].dropna().unique()) if "operating_airline" in df.columns else set())
    )
    total_airport_codes = len(
        set(df["origin"].dropna().unique())
        | (set(df["destination"].dropna().unique()) if "destination" in df.columns else set())
    )

    print(f"\n{'='*60}")
    print(f"AIRLINES: {len(missing_airlines)} unmatched out of {total_airline_codes} unique codes")
    print(f"{'='*60}")
    if missing_airlines:
        print(f"{'Code':<10} {'Occurrences':>12}")
        print(f"{'-'*10} {'-'*12}")
        for code, count in missing_airlines:
            print(f"{code:<10} {count:>12,}")
    else:
        print("All airline codes found in reference data.")

    print(f"\n{'='*60}")
    print(f"AIRPORTS: {len(missing_airports)} unmatched out of {total_airport_codes} unique codes")
    print(f"{'='*60}")
    if missing_airports:
        print(f"{'Code':<10} {'Occurrences':>12}")
        print(f"{'-'*10} {'-'*12}")
        for code, count in missing_airports:
            print(f"{code:<10} {count:>12,}")
    else:
        print("All airport codes found in reference data.")

    total_missing = len(missing_airlines) + len(missing_airports)
    if total_missing > 0:
        print(f"\nTotal: {total_missing} unmatched codes. "
              "Add them to _AIRLINE_OVERRIDES / _AIRPORT_OVERRIDES in the reference module.")
    else:
        print("\nAll codes matched. Reference data is complete for this dataset.")


if __name__ == "__main__":
    main()
