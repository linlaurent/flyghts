"""Abstract interface for flight data sources."""

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Protocol, Set, runtime_checkable


@dataclass
class RawFlight:
    """Minimal raw flight record from a source (before normalization)."""

    origin: str
    destination: str
    flight_no: str
    airline: str
    scheduled_time: Optional[str]
    status: Optional[str]
    date: date
    gate: Optional[str] = None
    terminal: Optional[str] = None
    cargo: Optional[bool] = None


@runtime_checkable
class FlightSource(Protocol):
    """Protocol for pluggable flight data sources."""

    def fetch_flights(self, flight_date: date, arrival: bool, cargo: bool) -> List[RawFlight]:
        """Fetch flights for a given date. arrival=True for arrivals, False for departures."""
        ...

    @property
    def supported_airports(self) -> Set[str]:
        """Set of IATA airport codes this source can provide data for."""
        ...
