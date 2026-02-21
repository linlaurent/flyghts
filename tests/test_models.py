"""Unit tests for audit models."""

from datetime import date, timedelta

import pytest

from flyghts.audit.models import DateFilter, Flight, QueryResult, RouteFilter


class TestRouteFilter:
    """Tests for RouteFilter."""

    def test_from_route_string(self) -> None:
        r = RouteFilter.from_route_string("HKG-TPE")
        assert r.origin == "HKG"
        assert r.destination == "TPE"
        assert r.bidirectional is True

    def test_from_route_string_bidirectional_false(self) -> None:
        r = RouteFilter.from_route_string("HKG-TPE", bidirectional=False)
        assert r.bidirectional is False

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid route format"):
            RouteFilter.from_route_string("HKGTPE")
        with pytest.raises(ValueError, match="Invalid route format"):
            RouteFilter.from_route_string("HKG-TPE-SIN")


class TestDateFilter:
    """Tests for DateFilter."""

    def test_single(self) -> None:
        d = date(2025, 2, 17)
        f = DateFilter.single(d)
        assert f.start_date == f.end_date == d

    def test_past_days(self) -> None:
        until = date(2025, 2, 18)
        f = DateFilter.past_days(3, until=until)
        assert f.start_date == date(2025, 2, 16)
        assert f.end_date == date(2025, 2, 18)

    def test_iter_dates(self) -> None:
        f = DateFilter.single(date(2025, 2, 17))
        dates = list(f.iter_dates())
        assert dates == [date(2025, 2, 17)]


class TestQueryResult:
    """Tests for QueryResult."""

    def test_to_dataframe_empty(self) -> None:
        r = QueryResult(flights=[])
        df = r.to_dataframe()
        assert len(df) == 0
        assert "origin" in df.columns

    def test_to_dataframe_with_flights(self) -> None:
        f = Flight(
            origin="HKG",
            destination="TPE",
            flight_no="CX421",
            airline="CX",
            scheduled_time=None,
            status="Departed",
            date=date(2025, 2, 17),
        )
        r = QueryResult(flights=[f])
        df = r.to_dataframe()
        assert len(df) == 1
        assert df.iloc[0]["origin"] == "HKG"
        assert df.iloc[0]["destination"] == "TPE"
