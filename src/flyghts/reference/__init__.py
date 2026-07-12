"""Reference data lookups for airports, airlines, alliances, and status parsing."""

from flyghts.reference.airlines import (
    AirlineInfo,
    get_airline,
    get_airline_by_iata,
    iata_to_icao,
)
from flyghts.reference.alliances import AllianceInfo, get_alliance, get_alliance_by_iata
from flyghts.reference.airports import AirportInfo, get_airport
from flyghts.reference.status import ParsedStatus, parse_status

__all__ = [
    "AirlineInfo",
    "AllianceInfo",
    "AirportInfo",
    "ParsedStatus",
    "get_airline",
    "get_airline_by_iata",
    "get_alliance",
    "get_alliance_by_iata",
    "get_airport",
    "iata_to_icao",
    "parse_status",
]
