"""Pluggable flight data sources."""

from flyghts.audit.sources.base import FlightSource, RawFlight
from flyghts.audit.sources.hk_airport import HKAirportSource
from flyghts.audit.sources.korea_airport import KoreaAirportSource

__all__ = ["FlightSource", "HKAirportSource", "KoreaAirportSource", "RawFlight"]
