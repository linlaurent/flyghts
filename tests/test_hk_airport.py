"""Unit tests for HK Airport API data retrieval."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from flyghts.audit.sources.hk_airport import HKAirportSource
from flyghts.audit.sources.base import RawFlight


# Sample API responses matching HK Airport API structure
DEPARTURE_ITEM = {
    "Destination": "TPE",
    "Terminal": "1",
    "Time": "08:30",
    "Gate": "23",
    "Flight number list": [
        {"No": "CX421", "Airline": "CX"},
    ],
    "Status": "Departed",
}

ARRIVAL_ITEM = {
    "Origin": "TPE",
    "Terminal": "1",
    "Time": "14:45",
    "Baggage": "A",
    "Flight number list": [
        {"No": "BR891", "Airline": "BR"},
    ],
    "Status": "Landed",
}


def _make_departures_response(date_str: str, items: list | None = None) -> dict:
    return {
        "Date": date_str,
        "Arrival": False,
        "Cargo": False,
        "List": items or [DEPARTURE_ITEM],
    }


def _make_arrivals_response(date_str: str, items: list | None = None) -> dict:
    return {
        "Date": date_str,
        "Arrival": True,
        "Cargo": False,
        "List": items or [ARRIVAL_ITEM],
    }


def _make_list_format_response(date_str: str, items: list | None = None) -> list:
    """API sometimes returns a list directly."""
    return items or [DEPARTURE_ITEM]


# New API format: list of wrappers with nested "list", destination/origin as arrays
def _make_departure_wrappers(date_str: str) -> list:
    return [
        {
            "date": date_str,
            "arrival": False,
            "cargo": False,
            "list": [
                {
                    "time": "23:20",
                    "flight": [{"no": "CX 271", "airline": "CPA"}],
                    "status": "Dep 01:21",
                    "destination": ["AMS"],
                    "terminal": "T1",
                    "gate": "29",
                },
            ],
        },
    ]


def _make_arrival_wrappers(date_str: str) -> list:
    return [
        {
            "date": date_str,
            "arrival": True,
            "cargo": False,
            "list": [
                {
                    "time": "23:55",
                    "flight": [{"no": "CX 587", "airline": "CPA"}],
                    "status": "At gate",
                    "origin": ["CTS"],
                },
            ],
        },
    ]


class TestHKAirportSourceFetchFlights:
    """Tests for fetch_flights with mocked HTTP."""

    @patch("flyghts.audit.sources.hk_airport.requests.get")
    def test_fetch_departures_dict_format(self, mock_get: MagicMock) -> None:
        """Departures with dict response (List key) are parsed correctly."""
        mock_get.return_value.json.return_value = _make_departures_response("2025-02-17")
        mock_get.return_value.raise_for_status = MagicMock()

        source = HKAirportSource()
        raw_flights = source.fetch_flights(date(2025, 2, 17), arrival=False, cargo=False)

        assert len(raw_flights) == 1
        r = raw_flights[0]
        assert r.origin == "HKG"
        assert r.destination == "TPE"
        assert r.flight_no == "CX421"
        assert r.airline == "CX"
        assert r.scheduled_time == "08:30"
        assert r.status == "Departed"
        assert r.date == date(2025, 2, 17)

    @patch("flyghts.audit.sources.hk_airport.requests.get")
    def test_fetch_arrivals_dict_format(self, mock_get: MagicMock) -> None:
        """Arrivals with dict response are parsed correctly."""
        mock_get.return_value.json.return_value = _make_arrivals_response("2025-02-17")
        mock_get.return_value.raise_for_status = MagicMock()

        source = HKAirportSource()
        raw_flights = source.fetch_flights(date(2025, 2, 17), arrival=True, cargo=False)

        assert len(raw_flights) == 1
        r = raw_flights[0]
        assert r.origin == "TPE"
        assert r.destination == "HKG"
        assert r.flight_no == "BR891"
        assert r.airline == "BR"
        assert r.scheduled_time == "14:45"
        assert r.status == "Landed"

    @patch("flyghts.audit.sources.hk_airport.requests.get")
    def test_fetch_flights_list_format(self, mock_get: MagicMock) -> None:
        """When API returns a list directly, parsing still works."""
        mock_get.return_value.json.return_value = _make_list_format_response("2025-02-17")
        mock_get.return_value.raise_for_status = MagicMock()

        source = HKAirportSource()
        raw_flights = source.fetch_flights(date(2025, 2, 17), arrival=False, cargo=False)

        assert len(raw_flights) >= 1
        r = raw_flights[0]
        assert r.origin == "HKG"
        assert r.destination == "TPE"
        assert r.flight_no == "CX421"

    @patch("flyghts.audit.sources.hk_airport.requests.get")
    def test_fetch_passes_correct_params(self, mock_get: MagicMock) -> None:
        """Request params match API spec."""
        mock_get.return_value.json.return_value = {"List": []}
        mock_get.return_value.raise_for_status = MagicMock()

        source = HKAirportSource()
        source.fetch_flights(date(2025, 2, 17), arrival=True, cargo=False)

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"]["date"] == "2025-02-17"
        assert call_kwargs["params"]["arrival"] == "true"
        assert call_kwargs["params"]["cargo"] == "false"
        assert call_kwargs["params"]["lang"] == "en"

    @patch("flyghts.audit.sources.hk_airport.requests.get")
    def test_empty_list_returns_empty(self, mock_get: MagicMock) -> None:
        """Empty List returns no flights."""
        mock_get.return_value.json.return_value = {"List": [], "Date": "2025-02-17"}
        mock_get.return_value.raise_for_status = MagicMock()

        source = HKAirportSource()
        raw_flights = source.fetch_flights(date(2025, 2, 17), arrival=False, cargo=False)

        assert raw_flights == []

    @patch("flyghts.audit.sources.hk_airport.requests.get")
    def test_fetch_wrapper_list_format(self, mock_get: MagicMock) -> None:
        """New API format: list of wrappers with nested list, destination/origin as arrays."""
        mock_get.return_value.json.side_effect = [
            _make_departure_wrappers("2026-02-20"),
            _make_arrival_wrappers("2026-02-20"),
        ]
        mock_get.return_value.raise_for_status = MagicMock()

        source = HKAirportSource()
        departures = source.fetch_flights(date(2026, 2, 20), arrival=False, cargo=False)
        arrivals = source.fetch_flights(date(2026, 2, 20), arrival=True, cargo=False)

        assert len(departures) == 1
        assert departures[0].origin == "HKG"
        assert departures[0].destination == "AMS"
        assert departures[0].flight_no == "CX 271"
        assert departures[0].airline == "CPA"

        assert len(arrivals) == 1
        assert arrivals[0].origin == "CTS"
        assert arrivals[0].destination == "HKG"
        assert arrivals[0].flight_no == "CX 587"

    @patch("flyghts.audit.sources.hk_airport.requests.get")
    def test_multiple_flights_in_item(self, mock_get: MagicMock) -> None:
        """Item with multiple flight numbers yields multiple RawFlights."""
        item = {
            "Destination": "TPE",
            "Time": "08:30",
            "Flight number list": [
                {"No": "CX421", "Airline": "CX"},
                {"No": "KA4871", "Airline": "KA"},
            ],
        }
        mock_get.return_value.json.return_value = _make_departures_response(
            "2025-02-17", items=[item]
        )
        mock_get.return_value.raise_for_status = MagicMock()

        source = HKAirportSource()
        raw_flights = source.fetch_flights(date(2025, 2, 17), arrival=False, cargo=False)

        assert len(raw_flights) == 2
        assert raw_flights[0].flight_no == "CX421" and raw_flights[0].airline == "CX"
        assert raw_flights[1].flight_no == "KA4871" and raw_flights[1].airline == "KA"


class TestHKAirportSourceRawToFlight:
    """Tests for raw_to_flight conversion."""

    def test_raw_to_flight_datetime_parsing(self) -> None:
        """Scheduled time is parsed to datetime."""
        source = HKAirportSource()
        raw = RawFlight(
            origin="HKG",
            destination="TPE",
            flight_no="CX421",
            airline="CX",
            scheduled_time="08:30",
            status="Departed",
            date=date(2025, 2, 17),
        )
        flight = source.raw_to_flight(raw)
        assert flight.scheduled_time is not None
        assert flight.scheduled_time.hour == 8
        assert flight.scheduled_time.minute == 30
        assert flight.date == date(2025, 2, 17)

    def test_raw_to_flight_no_time(self) -> None:
        """Missing scheduled_time yields None."""
        source = HKAirportSource()
        raw = RawFlight(
            origin="HKG",
            destination="TPE",
            flight_no="CX421",
            airline="CX",
            scheduled_time=None,
            status=None,
            date=date(2025, 2, 17),
        )
        flight = source.raw_to_flight(raw)
        assert flight.scheduled_time is None
        assert flight.origin == "HKG"
        assert flight.destination == "TPE"

    def test_supported_airports(self) -> None:
        """supported_airports returns HKG."""
        source = HKAirportSource()
        assert source.supported_airports == {"HKG"}
