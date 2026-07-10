"""Tests for US monthly Parquet data loading."""

import re
from pathlib import Path

import pandas as pd

US_PARQUET_PATTERN = re.compile(r"^\d{4}-\d{2}\.parquet$")

SAMPLE_ROW = {
    "origin": "JFK",
    "destination": "LAX",
    "flight_no": "AA 100",
    "airline": "AAL",
    "operating_flight_no": "AA 100",
    "operating_airline": "AAL",
    "scheduled_time": "2025-01-15 08:30:00",
    "status": "Arr 1145",
    "date": "2025-01-15",
    "cargo": False,
}


def _normalize_loaded_flights(df: pd.DataFrame) -> pd.DataFrame:
    """Mirror post-load normalization from the dashboard loader."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    if "cargo" in df.columns:

        def _to_bool(x):
            if pd.isna(x):
                return False
            if isinstance(x, bool):
                return x
            return str(x).lower() in ("true", "1", "yes")

        df["cargo"] = df["cargo"].apply(_to_bool)
    return df


def test_us_parquet_filename_convention() -> None:
    assert US_PARQUET_PATTERN.match("2025-01.parquet")
    assert US_PARQUET_PATTERN.match("2024-12.parquet")
    assert not US_PARQUET_PATTERN.match("2025-01-01.parquet")
    assert not US_PARQUET_PATTERN.match("2025-01.csv")


def test_parquet_roundtrip_dtypes(tmp_path: Path) -> None:
    parquet_path = tmp_path / "2025-01.parquet"
    pd.DataFrame([SAMPLE_ROW]).to_parquet(parquet_path, index=False)

    df = _normalize_loaded_flights(pd.read_parquet(parquet_path))

    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert df["cargo"].dtype == bool
    assert df["cargo"].iloc[0] == False
    assert df["origin"].iloc[0] == "JFK"
