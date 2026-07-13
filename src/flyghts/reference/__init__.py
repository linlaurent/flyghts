"""Reference data lookups for airports, airlines, alliances, and status parsing."""

from flyghts.reference.airlines import (
    AirlineInfo,
    get_airline,
    get_airline_by_iata,
    iata_to_icao,
    list_airlines,
)
from flyghts.reference.alliances import (
    AllianceInfo,
    get_alliance,
    get_alliance_by_iata,
    list_alliances,
)
from flyghts.reference.airports import AirportInfo, get_airport, list_airports
from flyghts.reference.coverage import CoverageGaps, find_missing_reference_codes
from flyghts.reference.status import ParsedStatus, parse_status

__all__ = [
    "AirlineInfo",
    "AllianceInfo",
    "AirportInfo",
    "CoverageGaps",
    "ParsedStatus",
    "find_missing_reference_codes",
    "get_airline",
    "get_airline_by_iata",
    "get_alliance",
    "get_alliance_by_iata",
    "get_airport",
    "iata_to_icao",
    "list_airlines",
    "list_airports",
    "list_alliances",
    "parse_status",
]
