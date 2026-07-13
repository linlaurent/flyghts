"""Find flight-data codes missing from reference airlines/airports."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pandas as pd

from flyghts.reference.airlines import get_airline
from flyghts.reference.airports import get_airport


@dataclass(frozen=True)
class CoverageGaps:
    """Unmatched airline and airport codes with occurrence counts."""

    missing_airlines: list[tuple[str, int]]
    missing_airports: list[tuple[str, int]]
    total_airline_codes: int
    total_airport_codes: int


def _count_codes(df: pd.DataFrame, columns: tuple[str, ...]) -> Counter[str]:
    codes: Counter[str] = Counter()
    for col in columns:
        if col not in df.columns:
            continue
        for val in df[col].dropna():
            code = str(val).strip()
            if code:
                codes[code] += 1
    return codes


def find_missing_reference_codes(df: pd.DataFrame) -> CoverageGaps:
    """Return airline/airport codes in ``df`` that are missing from reference data."""
    airline_codes = _count_codes(df, ("airline", "operating_airline"))
    airport_codes = _count_codes(df, ("origin", "destination"))

    missing_airlines = [
        (code, count)
        for code, count in airline_codes.most_common()
        if not get_airline(code)
    ]
    missing_airports = [
        (code, count)
        for code, count in airport_codes.most_common()
        if not get_airport(code)
    ]

    return CoverageGaps(
        missing_airlines=missing_airlines,
        missing_airports=missing_airports,
        total_airline_codes=len(airline_codes),
        total_airport_codes=len(airport_codes),
    )
