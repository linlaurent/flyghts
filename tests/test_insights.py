"""Tests for period-over-period flight insights."""

import pandas as pd

from flyghts.insights import (
    DEFAULT_COMPANY_AIRLINE_COL,
    DEFAULT_MIN_ABSOLUTE_CHANGE_PER_DAY,
    DEFAULT_MIN_PREVIOUS_FLIGHTS,
    DEFAULT_MIN_PERCENT_CHANGE,
    available_period_labels,
    compare_periods,
)


def _rows(
    date: str,
    airline: str,
    origin: str,
    destination: str,
    count: int,
) -> list[dict]:
    return [
        {
            "date": date,
            "airline": airline,
            "operating_airline": airline,
            "origin": origin,
            "destination": destination,
        }
        for _ in range(count)
    ]


def _sample_df() -> pd.DataFrame:
    rows: list[dict] = []
    rows += _rows("2025-01-06", "AAA", "HKG", "TPE", 20)
    rows += _rows("2025-01-06", "BBB", "HKG", "SIN", 5)
    rows += _rows("2025-01-06", "BBB", "SIN", "HKG", 4)
    rows += _rows("2025-01-07", "AAA", "HKG", "TPE", 8)

    rows += _rows("2025-01-13", "AAA", "HKG", "TPE", 7)
    rows += _rows("2025-01-13", "AAA", "HKG", "NRT", 2)
    rows += _rows("2025-01-13", "CCC", "HKG", "NRT", 3)
    rows += _rows("2025-01-14", "CCC", "HKG", "NRT", 2)
    return pd.DataFrame(rows)


def test_available_period_labels_returns_sorted_weekly_periods() -> None:
    labels = available_period_labels(_sample_df(), "weekly")

    assert labels == ["2025-01-06/2025-01-12", "2025-01-13/2025-01-19"]


def test_compare_periods_finds_new_companies_routes_and_company_routes() -> None:
    result = compare_periods(
        _sample_df(),
        period_kind="weekly",
        current_period=pd.Period("2025-01-13", freq="W-SUN"),
        min_previous_flights=10,
    )

    assert result.previous.label == "2025-01-06/2025-01-12"
    assert result.current.label == "2025-01-13/2025-01-19"
    assert set(result.new_companies["airline"]) == {"CCC"}
    assert set(result.disappeared_companies["airline"]) == {"BBB"}
    assert set(zip(result.new_routes["origin"], result.new_routes["destination"])) == {
        ("HKG", "NRT")
    }
    assert set(
        zip(
            result.new_company_routes["airline"],
            result.new_company_routes["origin"],
            result.new_company_routes["destination"],
        )
    ) == {("AAA", "HKG", "NRT"), ("CCC", "HKG", "NRT")}
    assert set(
        zip(
            result.disappeared_routes["origin"],
            result.disappeared_routes["destination"],
        )
    ) == {("HKG", "SIN"), ("SIN", "HKG")}
    assert set(
        zip(
            result.disappeared_company_routes["airline"],
            result.disappeared_company_routes["origin"],
            result.disappeared_company_routes["destination"],
        )
    ) == {("BBB", "HKG", "SIN"), ("BBB", "SIN", "HKG")}


def test_frequency_drops_use_observed_day_normalization_and_thresholds() -> None:
    result = compare_periods(
        _sample_df(),
        period_kind="weekly",
        current_period=pd.Period("2025-01-13", freq="W-SUN"),
        min_previous_flights=10,
        min_absolute_change_per_day=5.0,
        min_percent_change=25.0,
    )

    drops = result.frequency_drops

    assert len(drops) == 1
    drop = drops.iloc[0]
    assert drop["origin"] == "HKG"
    assert drop["destination"] == "TPE"
    assert drop["previous_flights"] == 28
    assert drop["current_flights"] == 7
    assert drop["previous_flights_per_day"] == 14.0
    assert drop["current_flights_per_day"] == 3.5
    assert drop["absolute_change_per_day"] == -10.5
    assert drop["percent_change"] == -75.0


def test_monthly_frequency_increases_are_reported() -> None:
    df = pd.DataFrame(
        _rows("2025-01-05", "AAA", "HKG", "TPE", 10)
        + _rows("2025-02-05", "AAA", "HKG", "TPE", 20)
    )

    result = compare_periods(
        df,
        period_kind="monthly",
        current_period=pd.Period("2025-02", freq="M"),
        min_previous_flights=5,
        min_absolute_change_per_day=5.0,
        min_percent_change=50.0,
    )

    assert result.frequency_drops.empty
    assert len(result.frequency_increases) == 1
    increase = result.frequency_increases.iloc[0]
    assert increase["origin"] == "HKG"
    assert increase["destination"] == "TPE"
    assert increase["percent_change"] == 100.0


def test_compare_periods_accepts_explicit_non_adjacent_comparison_period() -> None:
    df = pd.DataFrame(
        _rows("2025-01-06", "AAA", "HKG", "TPE", 4)
        + _rows("2025-01-13", "AAA", "HKG", "TPE", 8)
        + _rows("2025-01-20", "AAA", "HKG", "TPE", 12)
    )

    result = compare_periods(
        df,
        period_kind="weekly",
        current_period=pd.Period("2025-01-20", freq="W-SUN"),
        comparison_period=pd.Period("2025-01-06", freq="W-SUN"),
        min_previous_flights=1,
        min_absolute_change_per_day=1.0,
        min_percent_change=50.0,
    )

    assert result.previous.label == "2025-01-06/2025-01-12"
    assert result.current.label == "2025-01-20/2025-01-26"
    assert result.previous_total_flights == 4
    assert result.current_total_flights == 12
    increase = result.frequency_increases.iloc[0]
    assert increase["previous_flights"] == 4
    assert increase["current_flights"] == 12


def test_bidirectional_focus_airport_counts_arrivals_and_departures_together() -> None:
    df = pd.DataFrame(
        _rows("2025-01-06", "AAA", "HKG", "TPE", 2)
        + _rows("2025-01-06", "AAA", "TPE", "HKG", 3)
        + _rows("2025-01-13", "AAA", "HKG", "TPE", 7)
    )

    result = compare_periods(
        df,
        period_kind="weekly",
        current_period=pd.Period("2025-01-13", freq="W-SUN"),
        bidirectional_focus_airport="HKG",
        min_previous_flights=1,
        min_absolute_change_per_day=1.0,
        min_percent_change=10.0,
    )

    assert result.disappeared_routes.empty
    assert len(result.frequency_increases) == 1
    increase = result.frequency_increases.iloc[0]
    assert increase["origin"] == "HKG"
    assert increase["destination"] == "TPE"
    assert increase["previous_flights"] == 5
    assert increase["current_flights"] == 7


def test_default_company_dimension_is_marketing_airline() -> None:
    assert DEFAULT_COMPANY_AIRLINE_COL == "airline"

    df = pd.DataFrame(
        [
            {
                "date": "2025-01-06",
                "airline": "AAA",
                "operating_airline": "OOO",
                "origin": "HKG",
                "destination": "TPE",
            },
            {
                "date": "2025-01-13",
                "airline": "BBB",
                "operating_airline": "OOO",
                "origin": "HKG",
                "destination": "TPE",
            },
        ]
    )

    result = compare_periods(df, period_kind="weekly")

    assert set(result.new_companies["airline"]) == {"BBB"}


def test_default_minimum_change_per_day_is_quarter_flight() -> None:
    assert DEFAULT_MIN_ABSOLUTE_CHANGE_PER_DAY == 0.25


def test_default_minimum_previous_flights_is_one() -> None:
    assert DEFAULT_MIN_PREVIOUS_FLIGHTS == 1


def test_default_minimum_percent_change_is_five_percent() -> None:
    assert DEFAULT_MIN_PERCENT_CHANGE == 5.0
