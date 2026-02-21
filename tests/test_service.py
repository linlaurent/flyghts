"""Unit tests for AuditService data retrieval and filtering."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from flyghts.audit.models import DateFilter, Flight, QueryResult, RouteFilter
from flyghts.audit.service import AuditService
from flyghts.audit.sources.base import RawFlight


def _make_raw_flight(
    origin: str = "HKG",
    destination: str = "TPE",
    flight_no: str = "CX421",
    airline: str = "CX",
) -> RawFlight:
    return RawFlight(
        origin=origin,
        destination=destination,
        flight_no=flight_no,
        airline=airline,
        scheduled_time="08:30",
        status="Departed",
        date=date(2025, 2, 17),
    )


class TestAuditServiceQuery:
    """Tests for AuditService.query with mocked source."""

    def test_query_returns_filtered_flights(self) -> None:
        """Flights matching route filter are returned."""
        mock_source = MagicMock()
        raw_hkg_tpe = _make_raw_flight("HKG", "TPE")
        raw_tpe_hkg = _make_raw_flight("TPE", "HKG")
        mock_source.fetch_flights.side_effect = [
            [raw_hkg_tpe],
            [raw_tpe_hkg],
        ]
        mock_source.raw_to_flight.side_effect = lambda r: Flight(
            origin=r.origin,
            destination=r.destination,
            flight_no=r.flight_no,
            airline=r.airline,
            scheduled_time=None,
            status=r.status,
            date=r.date,
        )

        service = AuditService(source=mock_source)
        route = RouteFilter.from_route_string("HKG-TPE")
        date_filter = DateFilter.single(date(2025, 2, 17))
        result = service.query(route, date_filter)

        assert isinstance(result, QueryResult)
        assert len(result.flights) == 2
        origins_dests = {(f.origin, f.destination) for f in result.flights}
        assert origins_dests == {("HKG", "TPE"), ("TPE", "HKG")}

    def test_query_filters_non_matching_routes(self) -> None:
        """Flights not matching route are excluded."""
        mock_source = MagicMock()
        raw_sin = _make_raw_flight("HKG", "SIN")
        raw_tpe = _make_raw_flight("HKG", "TPE")
        mock_source.fetch_flights.side_effect = [
            [raw_sin, raw_tpe],
            [],
        ]
        mock_source.raw_to_flight.side_effect = lambda r: Flight(
            origin=r.origin,
            destination=r.destination,
            flight_no=r.flight_no,
            airline=r.airline,
            scheduled_time=None,
            status=r.status,
            date=r.date,
        )

        service = AuditService(source=mock_source)
        route = RouteFilter.from_route_string("HKG-TPE")
        date_filter = DateFilter.single(date(2025, 2, 17))
        result = service.query(route, date_filter)

        assert len(result.flights) == 1
        assert result.flights[0].destination == "TPE"

    def test_query_calls_source_for_each_date(self) -> None:
        """Source is called for departures and arrivals per date."""
        mock_source = MagicMock()
        mock_source.fetch_flights.return_value = []
        mock_source.raw_to_flight.side_effect = lambda r: Flight(
            origin=r.origin,
            destination=r.destination,
            flight_no=r.flight_no,
            airline=r.airline,
            scheduled_time=None,
            status=r.status,
            date=r.date,
        )

        service = AuditService(source=mock_source)
        route = RouteFilter.from_route_string("HKG-TPE")
        date_filter = DateFilter.past_days(2, until=date(2025, 2, 18))

        service.query(route, date_filter)

        assert mock_source.fetch_flights.call_count == 4
        calls = [c[1] for c in mock_source.fetch_flights.call_args_list]
        assert all(c["flight_date"] in (date(2025, 2, 17), date(2025, 2, 18)) for c in calls)
        assert sum(1 for c in calls if c["arrival"] is False) == 2
        assert sum(1 for c in calls if c["arrival"] is True) == 2
