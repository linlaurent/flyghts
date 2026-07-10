#!/usr/bin/env python3
"""
Migrate US daily CSV files to monthly Parquet files.

Reads data/us/YYYY-MM-DD.csv files, groups by month, writes data/us/YYYY-MM.parquet,
and deletes the source CSVs.

Usage:
    uv run python scripts/migrate_us_csv_to_parquet.py
    uv run python scripts/migrate_us_csv_to_parquet.py --data-dir data/us/
    uv run python scripts/migrate_us_csv_to_parquet.py --force
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "us"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate US daily CSV files to monthly Parquet files"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(DEFAULT_DATA_DIR),
        help="US data directory (default: data/us/)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing Parquet files",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Data directory not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    csv_files = sorted(data_dir.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {data_dir}", file=sys.stderr)
        sys.exit(1)

    dfs = [pd.read_csv(f) for f in csv_files]
    combined = pd.concat(dfs, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"], format="%Y-%m-%d")
    combined["_month"] = combined["date"].dt.to_period("M").astype(str)

    n_written = 0
    n_removed = 0
    migrated_months: set[str] = set()
    for month_str, group in combined.groupby("_month"):
        out = data_dir / f"{month_str}.parquet"
        if out.exists() and not args.force:
            print(
                f"Skipping {out.name} (already exists, use --force to overwrite)",
                file=sys.stderr,
            )
            migrated_months.add(month_str)
            continue
        group = group.drop(columns="_month")
        group.to_parquet(out, index=False)
        n_written += len(group)
        migrated_months.add(month_str)
        print(f"Wrote {len(group):,} flights to {out.name}", file=sys.stderr)

    for csv_file in csv_files:
        month_str = csv_file.stem[:7]
        if month_str in migrated_months:
            csv_file.unlink()
            n_removed += 1

    n_months = combined["_month"].nunique()
    print(
        f"Migrated {n_written:,} flights into {n_months} monthly Parquet files; "
        f"removed {n_removed} daily CSVs from {data_dir}/",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
