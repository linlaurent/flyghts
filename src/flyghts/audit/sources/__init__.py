"""Pluggable flight data sources."""

from flyghts.audit.sources.base import FlightSource, RawFlight
from flyghts.audit.sources.hk_airport import HKAirportSource

__all__ = ["FlightSource", "HKAirportSource", "RawFlight"]
