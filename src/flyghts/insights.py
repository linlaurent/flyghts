"""Period-over-period flight insights."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

PeriodKind = Literal["weekly", "monthly"]

MARKETING_AIRLINE_COL = "airline"
OPERATING_AIRLINE_COL = "operating_airline"
DEFAULT_COMPANY_AIRLINE_COL = MARKETING_AIRLINE_COL
DEFAULT_MIN_PREVIOUS_FLIGHTS = 1
DEFAULT_MIN_ABSOLUTE_CHANGE_PER_DAY = 0.25
DEFAULT_MIN_PERCENT_CHANGE = 5.0

_PERIOD_FREQ: dict[PeriodKind, str] = {
    "weekly": "W-SUN",
    "monthly": "M",
}


@dataclass(frozen=True)
class PeriodWindow:
    """A selected comparison period."""

    period: pd.Period
    label: str
    start: pd.Timestamp
    end: pd.Timestamp
    observed_days: int


@dataclass(frozen=True)
class PeriodInsightResult:
    """Structured insight tables for one current period vs a comparison period."""

    period_kind: PeriodKind
    previous: PeriodWindow
    current: PeriodWindow
    previous_total_flights: int
    current_total_flights: int
    new_companies: pd.DataFrame
    disappeared_companies: pd.DataFrame
    new_routes: pd.DataFrame
    new_company_routes: pd.DataFrame
    disappeared_routes: pd.DataFrame
    disappeared_company_routes: pd.DataFrame
    frequency_drops: pd.DataFrame
    frequency_increases: pd.DataFrame


def available_period_labels(df: pd.DataFrame, period_kind: PeriodKind) -> list[str]:
    """Return available period labels for selector controls."""
    if df.empty:
        return []
    periods = _period_series(df, period_kind).dropna().sort_values().unique()
    return [str(period) for period in periods]


def compare_periods(
    df: pd.DataFrame,
    *,
    period_kind: PeriodKind,
    current_period: str | pd.Period | None = None,
    comparison_period: str | pd.Period | None = None,
    airline_col: str = DEFAULT_COMPANY_AIRLINE_COL,
    bidirectional_focus_airport: str | None = None,
    min_previous_flights: int = DEFAULT_MIN_PREVIOUS_FLIGHTS,
    min_absolute_change_per_day: float = DEFAULT_MIN_ABSOLUTE_CHANGE_PER_DAY,
    min_percent_change: float = DEFAULT_MIN_PERCENT_CHANGE,
) -> PeriodInsightResult:
    """Compare the selected period against a same-frequency comparison period.

    Rows are treated as directional flight legs unless bidirectional_focus_airport
    is provided. In that case, routes touching the focus airport are normalized to
    focus -> counterpart so arrivals and departures are counted together.
    Frequency thresholds are applied to route-level flights-per-day values so weeks
    and months can be compared.
    """
    _validate_input(df, airline_col)

    work = df.copy()
    work["date"] = pd.to_datetime(work["date"]).dt.normalize()
    work["_period"] = _period_series(work, period_kind)
    selected = _resolve_period(work["_period"], period_kind, current_period)
    previous = (
        _resolve_period(work["_period"], period_kind, comparison_period)
        if comparison_period is not None
        else selected - 1
    )
    if bidirectional_focus_airport:
        work = _normalize_focus_routes(work, bidirectional_focus_airport)

    current_df = work[work["_period"] == selected].copy()
    previous_df = work[work["_period"] == previous].copy()

    current_window = _window_for(current_df, selected)
    previous_window = _window_for(previous_df, previous)

    company_comparison = _compare_key_counts(
        previous_df,
        current_df,
        [airline_col],
        previous_window.observed_days,
        current_window.observed_days,
    )
    route_comparison = _compare_key_counts(
        previous_df,
        current_df,
        ["origin", "destination"],
        previous_window.observed_days,
        current_window.observed_days,
    )
    company_route_comparison = _compare_key_counts(
        previous_df,
        current_df,
        [airline_col, "origin", "destination"],
        previous_window.observed_days,
        current_window.observed_days,
    )

    new_companies = _new_keys(company_comparison).rename(
        columns={airline_col: "airline"}
    )
    disappeared_companies = _lost_keys(company_comparison).rename(
        columns={airline_col: "airline"}
    )
    new_routes = _new_keys(route_comparison)
    new_company_routes = _new_keys(company_route_comparison).rename(
        columns={airline_col: "airline"}
    )
    disappeared_routes = _lost_keys(route_comparison)
    disappeared_company_routes = _lost_keys(company_route_comparison).rename(
        columns={airline_col: "airline"}
    )

    frequency_drops = _frequency_changes(
        route_comparison,
        min_previous_flights=min_previous_flights,
        min_absolute_change_per_day=min_absolute_change_per_day,
        min_percent_change=min_percent_change,
        direction="drop",
    )
    frequency_increases = _frequency_changes(
        route_comparison,
        min_previous_flights=min_previous_flights,
        min_absolute_change_per_day=min_absolute_change_per_day,
        min_percent_change=min_percent_change,
        direction="increase",
    )

    return PeriodInsightResult(
        period_kind=period_kind,
        previous=previous_window,
        current=current_window,
        previous_total_flights=len(previous_df),
        current_total_flights=len(current_df),
        new_companies=new_companies,
        disappeared_companies=disappeared_companies,
        new_routes=new_routes,
        new_company_routes=new_company_routes,
        disappeared_routes=disappeared_routes,
        disappeared_company_routes=disappeared_company_routes,
        frequency_drops=frequency_drops,
        frequency_increases=frequency_increases,
    )


def _validate_input(df: pd.DataFrame, airline_col: str) -> None:
    required = {"date", "origin", "destination", airline_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    if df.empty:
        raise ValueError("Cannot compare periods for an empty dataframe.")


def _period_series(df: pd.DataFrame, period_kind: PeriodKind) -> pd.Series:
    try:
        freq = _PERIOD_FREQ[period_kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported period kind: {period_kind}") from exc
    dates = pd.to_datetime(df["date"])
    return dates.dt.to_period(freq)


def _resolve_period(
    periods: pd.Series,
    period_kind: PeriodKind,
    current_period: str | pd.Period | None,
) -> pd.Period:
    if current_period is None:
        return periods.max()
    if isinstance(current_period, pd.Period):
        return current_period.asfreq(_PERIOD_FREQ[period_kind])
    return pd.Period(current_period, freq=_PERIOD_FREQ[period_kind])


def _window_for(df: pd.DataFrame, period: pd.Period) -> PeriodWindow:
    start = period.start_time.normalize()
    end = period.end_time.normalize()
    observed_days = int(df["date"].nunique()) if not df.empty else 0
    return PeriodWindow(
        period=period,
        label=str(period),
        start=start,
        end=end,
        observed_days=observed_days,
    )


def _normalize_focus_routes(df: pd.DataFrame, focus_airport: str) -> pd.DataFrame:
    """Normalize routes touching a focus airport to focus -> counterpart."""
    normalized = df.copy()
    touches_focus = (normalized["origin"] == focus_airport) | (
        normalized["destination"] == focus_airport
    )
    counterpart = normalized["destination"].where(
        normalized["origin"] == focus_airport,
        normalized["origin"],
    )
    normalized.loc[touches_focus, "origin"] = focus_airport
    normalized.loc[touches_focus, "destination"] = counterpart[touches_focus]
    return normalized


def _compare_key_counts(
    previous_df: pd.DataFrame,
    current_df: pd.DataFrame,
    keys: list[str],
    previous_days: int,
    current_days: int,
) -> pd.DataFrame:
    previous = previous_df.groupby(keys).size().rename("previous_flights")
    current = current_df.groupby(keys).size().rename("current_flights")
    comparison = (
        pd.concat([previous, current], axis=1)
        .fillna(0)
        .astype({"previous_flights": int, "current_flights": int})
        .reset_index()
    )
    comparison["previous_flights_per_day"] = comparison["previous_flights"] / max(
        previous_days, 1
    )
    comparison["current_flights_per_day"] = comparison["current_flights"] / max(
        current_days, 1
    )
    comparison["absolute_change_per_day"] = (
        comparison["current_flights_per_day"] - comparison["previous_flights_per_day"]
    )
    comparison["percent_change"] = float("nan")
    has_previous = comparison["previous_flights_per_day"] > 0
    comparison.loc[has_previous, "percent_change"] = (
        100
        * comparison.loc[has_previous, "absolute_change_per_day"]
        / comparison.loc[has_previous, "previous_flights_per_day"]
    )
    return comparison


def _new_keys(comparison: pd.DataFrame) -> pd.DataFrame:
    rows = comparison[
        (comparison["previous_flights"] == 0) & (comparison["current_flights"] > 0)
    ].copy()
    return _sort_and_round(rows, ["current_flights_per_day"], ascending=[False])


def _lost_keys(comparison: pd.DataFrame) -> pd.DataFrame:
    rows = comparison[
        (comparison["previous_flights"] > 0) & (comparison["current_flights"] == 0)
    ].copy()
    return _sort_and_round(rows, ["previous_flights_per_day"], ascending=[False])


def _frequency_changes(
    comparison: pd.DataFrame,
    *,
    min_previous_flights: int,
    min_absolute_change_per_day: float,
    min_percent_change: float,
    direction: Literal["drop", "increase"],
) -> pd.DataFrame:
    if direction == "drop":
        rows = comparison[
            (comparison["previous_flights"] >= min_previous_flights)
            & (comparison["absolute_change_per_day"] <= -min_absolute_change_per_day)
            & (comparison["percent_change"] <= -min_percent_change)
        ].copy()
        return _sort_and_round(rows, ["absolute_change_per_day"], ascending=[True])

    rows = comparison[
        (comparison["previous_flights"] >= min_previous_flights)
        & (comparison["absolute_change_per_day"] >= min_absolute_change_per_day)
        & (comparison["percent_change"] >= min_percent_change)
    ].copy()
    return _sort_and_round(rows, ["absolute_change_per_day"], ascending=[False])


def _sort_and_round(
    df: pd.DataFrame, by: list[str], *, ascending: list[bool]
) -> pd.DataFrame:
    if df.empty:
        return df
    rounded = df.sort_values(by=by, ascending=ascending).reset_index(drop=True)
    for col in [
        "previous_flights_per_day",
        "current_flights_per_day",
        "absolute_change_per_day",
        "percent_change",
    ]:
        if col in rounded.columns:
            rounded[col] = rounded[col].astype("Float64").round(2)
    return rounded
