"""Unit tests for reference lookups and status parsing."""

import pytest

from flyghts.reference import (
    AirlineInfo,
    AllianceInfo,
    AirportInfo,
    ParsedStatus,
    find_missing_reference_codes,
    get_airline,
    get_airport,
    get_alliance,
    get_alliance_by_iata,
    list_airlines,
    list_airports,
    list_alliances,
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

    def test_province_china(self) -> None:
        info = get_airport("CAN")
        assert info is not None
        assert info.province == "Guangdong Province"

    def test_province_us(self) -> None:
        info = get_airport("ATL")
        assert info is not None
        assert info.province == "Georgia"


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

    def test_cpa_includes_iata(self) -> None:
        info = get_airline("CPA")
        assert info is not None
        assert info.iata == "CX"


class TestListReference:
    """Tests for bulk list helpers."""

    def test_list_airlines_includes_cathay(self) -> None:
        airlines = list_airlines()
        assert len(airlines) > 1000
        by_icao = {a.icao: a for a in airlines}
        assert "CPA" in by_icao
        assert by_icao["CPA"].iata == "CX"
        assert airlines == sorted(airlines, key=lambda a: a.icao)

    def test_list_airports_includes_hkg(self) -> None:
        airports = list_airports()
        assert len(airports) > 1000
        by_iata = {a.iata: a for a in airports}
        assert "HKG" in by_iata
        assert airports == sorted(airports, key=lambda a: a.iata)

    def test_list_alliances_includes_members_and_affiliates(self) -> None:
        all_rows = list_alliances(members_only=False)
        members = list_alliances(members_only=True)
        assert len(all_rows) > len(members)
        assert any(a.icao == "CPA" and a.alliance == "oneworld" for a in members)
        assert any(a.alliance_type == "affiliate" for a in all_rows)
        assert not any(a.alliance_type == "affiliate" for a in members)
        ended = [a for a in members if a.to_date is not None]
        assert ended
        assert any(a.icao == "CSN" and a.to_date is not None for a in members)


class TestCoverageGaps:
    """Tests for find_missing_reference_codes."""

    def test_known_codes_have_no_gaps(self) -> None:
        import pandas as pd

        df = pd.DataFrame(
            {
                "airline": ["CPA", "CPA"],
                "operating_airline": ["CPA", "CPA"],
                "origin": ["HKG", "HKG"],
                "destination": ["NRT", "ICN"],
            }
        )
        gaps = find_missing_reference_codes(df)
        assert gaps.missing_airlines == []
        assert gaps.missing_airports == []
        assert gaps.total_airline_codes == 1
        assert gaps.total_airport_codes == 3

    def test_reports_missing_codes_by_frequency(self) -> None:
        import pandas as pd

        df = pd.DataFrame(
            {
                "airline": ["ZZQ", "ZZQ", "YYQ"],
                "operating_airline": ["ZZQ", "ZZQ", "YYQ"],
                "origin": ["HKG", "QQQ", "QQQ"],
                "destination": ["NRT", "QQQ", "HKG"],
            }
        )
        gaps = find_missing_reference_codes(df)
        assert gaps.missing_airlines == [("ZZQ", 4), ("YYQ", 2)]
        assert gaps.missing_airports == [("QQQ", 3)]
        assert gaps.total_airline_codes == 2
        assert gaps.total_airport_codes == 3


class TestGetAlliance:
    """Tests for alliance membership lookup."""

    def test_cathay_oneworld_by_icao(self) -> None:
        info = get_alliance("CPA")
        assert info is not None
        assert isinstance(info, AllianceInfo)
        assert info.alliance == "oneworld"
        assert info.alliance_type == "member"
        assert info.is_member
        assert info.from_date is not None

    def test_cathay_by_iata(self) -> None:
        info = get_alliance_by_iata("CX")
        assert info is not None
        assert info.alliance == "oneworld"

    def test_delta_skyteam(self) -> None:
        info = get_alliance("DAL")
        assert info is not None
        assert info.alliance == "skyteam"

    def test_united_star_alliance(self) -> None:
        info = get_alliance("UAL")
        assert info is not None
        assert info.alliance == "star_alliance"

    def test_unknown_returns_none(self) -> None:
        assert get_alliance("ZZQ") is None
        assert get_alliance_by_iata("ZZ") is None

    def test_empty_returns_none(self) -> None:
        assert get_alliance("") is None
        assert get_alliance_by_iata("") is None

    def test_members_only_filters_affiliates(self) -> None:
        # Horizon Air (QX) is a oneworld affiliate in OPTD
        assert get_alliance_by_iata("QX", members_only=True) is None
        affiliate = get_alliance_by_iata("QX", members_only=False)
        assert affiliate is not None
        assert affiliate.alliance_type == "affiliate"
        assert affiliate.alliance == "oneworld"

    def test_point_in_time_ended_membership(self) -> None:
        from datetime import date

        # China Southern left SkyTeam end of 2018 in OPTD
        during = get_alliance("CSN", as_of=date(2015, 6, 1))
        assert during is not None
        assert during.alliance == "skyteam"
        assert during.to_date == date(2018, 12, 31)

        after = get_alliance("CSN", as_of=date(2019, 1, 1))
        assert after is None

        before = get_alliance("CSN", as_of=date(2007, 1, 1))
        assert before is None

    def test_point_in_time_alliance_switch(self) -> None:
        from datetime import date

        # Continental: SkyTeam then Star Alliance in OPTD
        sky = get_alliance("COA", as_of=date(2008, 1, 1))
        assert sky is not None and sky.alliance == "skyteam"
        star = get_alliance("COA", as_of=date(2010, 6, 1))
        assert star is not None and star.alliance == "star_alliance"
        later = get_alliance("COA", as_of=date(2015, 1, 1))
        assert later is None


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
