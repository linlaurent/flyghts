"""Audit service - orchestration, filtering, and query execution."""

from flyghts.audit.models import AuditQuery, DateFilter, Flight, QueryResult, RouteFilter
from flyghts.audit.sources.hk_airport import HKAirportSource


class AuditService:
    """Orchestrates flight data fetching, filtering, and statistics."""

    def __init__(self, source=None):
        self._source = source or HKAirportSource()

    def query(self, route: RouteFilter, date_filter: DateFilter) -> QueryResult:
        """Fetch and filter flights for the given route and date range."""
        all_flights = []

        for d in date_filter.iter_dates():
            raw_flights = []
            # Departures from origin -> destination (e.g. HKG -> TPE)
            raw_flights.extend(
                self._source.fetch_flights(flight_date=d, arrival=False, cargo=False)
            )
            # Arrivals from destination -> origin (e.g. TPE -> HKG)
            raw_flights.extend(
                self._source.fetch_flights(flight_date=d, arrival=True, cargo=False)
            )

            for raw in raw_flights:
                flight = self._source.raw_to_flight(raw)
                if self._matches_route(flight, route):
                    all_flights.append(flight)

        return QueryResult(
            flights=all_flights,
            query=AuditQuery(route=route, date_filter=date_filter),
        )

    def _matches_route(self, flight: Flight, route: RouteFilter) -> bool:
        """Check if flight matches the route filter."""
        if route.bidirectional:
            pairs = [
                (route.origin, route.destination),
                (route.destination, route.origin),
            ]
        else:
            pairs = [(route.origin, route.destination)]

        for orig, dest in pairs:
            if orig and flight.origin != orig:
                continue
            if dest and flight.destination != dest:
                continue
            return True
        return False

    def statistics(self, flights):
        """Compute statistics for the given flights."""
        from flyghts.audit.stats import compute_stats

        return compute_stats(flights)
