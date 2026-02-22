"""Unit tests for reference lookups and status parsing."""

import pytest

from flyghts.reference import (
    AirlineInfo,
    AirportInfo,
    ParsedStatus,
    get_airline,
    get_airport,
    parse_status,
)


class TestGetAirport:
    """Tests for get_airport."""

    def test_hkg(self) -> None:
        info = get_airport("HKG")
        assert info is not None
        assert isinstance(info, AirportInfo)
        assert info.iata == "HKG"
        assert "Hong Kong" in info.name or "Chek Lap Kok" in info.name
        assert info.country == "Hong Kong"
        assert info.latitude != 0 or info.longitude != 0

    def test_icn(self) -> None:
        info = get_airport("ICN")
        assert info is not None
        assert info.iata == "ICN"
        assert "Incheon" in info.name or "Seoul" in info.city

    def test_unknown_returns_none(self) -> None:
        assert get_airport("XXX") is None
        assert get_airport("ZZZ") is None

    def test_empty_returns_none(self) -> None:
        assert get_airport("") is None

    def test_case_insensitive(self) -> None:
        info1 = get_airport("hkg")
        info2 = get_airport("HKG")
        assert info1 is not None and info2 is not None
        assert info1.iata == info2.iata


class TestGetAirline:
    """Tests for get_airline."""

    def test_cpa_cathay(self) -> None:
        info = get_airline("CPA")
        assert info is not None
        assert isinstance(info, AirlineInfo)
        assert info.icao == "CPA"
        assert "Cathay" in info.name or "Dragon" in info.name
        assert "Hong Kong" in info.country

    def test_ana(self) -> None:
        info = get_airline("ANA")
        assert info is not None
        assert "Nippon" in info.name or "ANA" in info.name
        assert info.country == "Japan"

    def test_unknown_returns_none(self) -> None:
        assert get_airline("ZZQ") is None  # Non-existent ICAO

    def test_empty_returns_none(self) -> None:
        assert get_airline("") is None

    def test_case_insensitive(self) -> None:
        info1 = get_airline("cpa")
        info2 = get_airline("CPA")
        assert info1 is not None and info2 is not None
        assert info1.icao == info2.icao


class TestParseStatus:
    """Tests for parse_status."""

    def test_dep_time_only(self) -> None:
        p = parse_status("Dep 00:13")
        assert p.status_type == "departed"
        assert p.actual_time == "00:13"
        assert p.actual_date is None

    def test_dep_with_date(self) -> None:
        p = parse_status("Dep 23:55 (31/12/2025)")
        assert p.status_type == "departed"
        assert p.actual_time == "23:55"
        assert p.actual_date == "2025-12-31"

    def test_arr(self) -> None:
        p = parse_status("Arr 14:30")
        assert p.status_type == "arrived"
        assert p.actual_time == "14:30"

    def test_at_gate(self) -> None:
        p = parse_status("At gate 00:00 (02/01/2026)")
        assert p.status_type == "at_gate"
        assert p.actual_time == "00:00"
        assert p.actual_date == "2026-01-02"

    def test_cancelled(self) -> None:
        p = parse_status("Cancelled")
        assert p.status_type == "cancelled"
        assert p.actual_time is None
        assert p.actual_date is None

    def test_delayed(self) -> None:
        p = parse_status("Delayed")
        assert p.status_type == "delayed"
        assert p.actual_time is None

    def test_none_or_empty_unknown(self) -> None:
        assert parse_status(None).status_type == "unknown"
        assert parse_status("").status_type == "unknown"

    def test_unparseable_unknown(self) -> None:
        p = parse_status("Boarding")
        assert p.status_type == "unknown"
        assert p.actual_time is None
