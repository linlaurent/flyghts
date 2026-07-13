#!/usr/bin/env python3
"""
Validate flight data files against reference data (airlines.json / airports.json).

Scans flight CSV and Parquet files and reports airline codes and airport codes
that are not found in the reference data, sorted by frequency. Helps identify
which entries need to be added to _AIRLINE_OVERRIDES / _AIRPORT_OVERRIDES.

Usage:
    uv run python scripts/validate_reference_data.py                        # all sources
    uv run python scripts/validate_reference_data.py --data-dir data/us/
    uv run python scripts/validate_reference_data.py --data-dir data/hkg/
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from flyghts.reference import find_missing_reference_codes

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


def _load_all_flights(data_dir: Path) -> pd.DataFrame:
    """Load all CSV and Parquet files from a directory (recursively)."""
    csv_files = sorted(data_dir.rglob("*.csv"))
    parquet_files = sorted(data_dir.rglob("*.parquet"))
    if not csv_files and not parquet_files:
        print(f"No flight data files found in {data_dir}", file=sys.stderr)
        sys.exit(1)
    dfs = [pd.read_csv(f, dtype=str) for f in csv_files]
    dfs.extend(pd.read_parquet(f).astype(str) for f in parquet_files)
    df = pd.concat(dfs, ignore_index=True)
    n_files = len(csv_files) + len(parquet_files)
    print(f"Loaded {len(df)} rows from {n_files} files in {data_dir}", file=sys.stderr)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate flight data files against reference data"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Directory to scan (default: data/ with all subdirectories)",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_DATA_DIR
    df = _load_all_flights(data_dir)
    gaps = find_missing_reference_codes(df)

    print(f"\n{'=' * 60}")
    print(
        f"AIRLINES: {len(gaps.missing_airlines)} unmatched "
        f"out of {gaps.total_airline_codes} unique codes"
    )
    print(f"{'=' * 60}")
    if gaps.missing_airlines:
        print(f"{'Code':<10} {'Occurrences':>12}")
        print(f"{'-' * 10} {'-' * 12}")
        for code, count in gaps.missing_airlines:
            print(f"{code:<10} {count:>12,}")
    else:
        print("All airline codes found in reference data.")

    print(f"\n{'=' * 60}")
    print(
        f"AIRPORTS: {len(gaps.missing_airports)} unmatched "
        f"out of {gaps.total_airport_codes} unique codes"
    )
    print(f"{'=' * 60}")
    if gaps.missing_airports:
        print(f"{'Code':<10} {'Occurrences':>12}")
        print(f"{'-' * 10} {'-' * 12}")
        for code, count in gaps.missing_airports:
            print(f"{code:<10} {count:>12,}")
    else:
        print("All airport codes found in reference data.")

    total_missing = len(gaps.missing_airlines) + len(gaps.missing_airports)
    if total_missing > 0:
        print(
            f"\nTotal: {total_missing} unmatched codes. "
            "Add them to _AIRLINE_OVERRIDES / _AIRPORT_OVERRIDES in the reference module."
        )
    else:
        print("\nAll codes matched. Reference data is complete for this dataset.")


if __name__ == "__main__":
    main()
