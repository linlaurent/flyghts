"""Data models for flight audit."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional


@dataclass
class Flight:
    """Normalized flight record."""

    origin: str
    destination: str
    flight_no: str
    airline: str
    scheduled_time: Optional[datetime]
    status: Optional[str]
    date: date
    # Optional HK-specific fields
    gate: Optional[str] = None
    terminal: Optional[str] = None
    cargo: Optional[bool] = None

    def route(self) -> str:
        """Return route as ORIGIN-DESTINATION."""
        return f"{self.origin}-{self.destination}"


@dataclass
class RouteFilter:
    """Filter for origin and/or destination (IATA codes)."""

    origin: Optional[str] = None
    destination: Optional[str] = None
    bidirectional: bool = False

    @classmethod
    def from_route_string(cls, route: str, bidirectional: bool = True) -> "RouteFilter":
        """
        Parse route string like 'HKG-TPE' or 'TPE-HKG'.
        Returns filter for both directions when bidirectional=True.
        """
        parts = route.upper().split("-")
        if len(parts) != 2:
            raise ValueError(f"Invalid route format: {route}. Expected ORIGIN-DEST (e.g. HKG-TPE)")
        return cls(
            origin=parts[0].strip(),
            destination=parts[1].strip(),
            bidirectional=bidirectional,
        )


@dataclass
class DateFilter:
    """Filter for single date or date range."""

    start_date: date
    end_date: Optional[date] = None

    @classmethod
    def single(cls, d: date) -> "DateFilter":
        """Create filter for a single date."""
        return cls(start_date=d, end_date=d)

    @classmethod
    def past_days(cls, days: int, until: Optional[date] = None) -> "DateFilter":
        """Create filter for past N days (inclusive)."""
        end = until or date.today()
        from datetime import timedelta

        start = end - timedelta(days=days - 1)
        return cls(start_date=start, end_date=end)

    def iter_dates(self):
        """Iterate over all dates in the range (inclusive)."""
        from datetime import timedelta

        d = self.start_date
        end = self.end_date or self.start_date
        while d <= end:
            yield d
            d += timedelta(days=1)


@dataclass
class AuditQuery:
    """Combines route and date filters."""

    route: RouteFilter
    date_filter: DateFilter


@dataclass
class QueryResult:
    """Result of an audit query."""

    flights: List[Flight] = field(default_factory=list)
    query: Optional[AuditQuery] = None

    def to_dataframe(self):
        """Convert to pandas DataFrame."""
        import pandas as pd

        if not self.flights:
            return pd.DataFrame(
                columns=[
                    "origin",
                    "destination",
                    "flight_no",
                    "airline",
                    "scheduled_time",
                    "status",
                    "date",
                ]
            )
        return pd.DataFrame(
            [
                {
                    "origin": f.origin,
                    "destination": f.destination,
                    "flight_no": f.flight_no,
                    "airline": f.airline,
                    "scheduled_time": f.scheduled_time,
                    "status": f.status,
                    "date": f.date,
                }
                for f in self.flights
            ]
        )
