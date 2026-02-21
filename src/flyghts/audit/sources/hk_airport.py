"""Hong Kong International Airport flight information API client."""

from datetime import date, datetime
from typing import Any, List, Optional, Set

import requests

from flyghts.audit.models import Flight
from flyghts.audit.sources.base import RawFlight

BASE_URL = "https://www.hongkongairport.com/flightinfo-rest/rest/flights/past"
HKG = "HKG"


class HKAirportSource:
    """Flight data source using HK Airport open API."""

    def __init__(self, base_url: str = BASE_URL, timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout

    def fetch_flights(self, flight_date: date, arrival: bool, cargo: bool) -> List[RawFlight]:
        """Fetch flights from HK Airport API. arrival=True for arrivals, False for departures."""
        params = {
            "date": flight_date.strftime("%Y-%m-%d"),
            "arrival": str(arrival).lower(),
            "cargo": str(cargo).lower(),
            "lang": "en",
        }
        resp = requests.get(self.base_url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        flights = []
        if isinstance(data, list):
            if data and isinstance(data[0], dict) and ("list" in data[0] or "List" in data[0]):
                for wrapper in data:
                    items = wrapper.get("list") or wrapper.get("List") or []
                    date_str = wrapper.get("date") or wrapper.get("Date") or flight_date.strftime("%Y-%m-%d")
                    for item in items:
                        for raw in self._parse_list_item(item, date_str, arrival):
                            flights.append(raw)
            else:
                date_str = flight_date.strftime("%Y-%m-%d")
                for item in data:
                    for raw in self._parse_list_item(item, date_str, arrival):
                        flights.append(raw)
        else:
            flight_list = data.get("List") or data.get("list") or []
            date_str = data.get("Date") or data.get("date") or flight_date.strftime("%Y-%m-%d")
            for item in flight_list:
                for raw in self._parse_list_item(item, date_str, arrival):
                    flights.append(raw)

        return flights

    def _parse_list_item(
        self, item: dict, date_str: str, arrival: bool
    ) -> List[RawFlight]:
        """Parse a single list item from the API response (may contain multiple flight numbers)."""
        if arrival:
            origin = self._get_str_or_first(
                item,
                "Origin", "origin", "Port of origin", "portOfOrigin",
                "From", "from", "dep_iata", "dep",
            )
            destination = HKG
        else:
            origin = HKG
            destination = self._get_str_or_first(
                item,
                "Destination", "destination", "Port of destination", "portOfDestination",
                "To", "to", "arr_iata", "arr",
            )

        time_str = self._get_str(item, "Time", "time", "ScheduledTime", "scheduledTime")
        status = self._get_str(item, "Status", "status")
        gate = self._get_str(item, "Gate", "gate")
        terminal = self._get_str(item, "Terminal", "terminal")

        flight_nos = (
            item.get("flight")
            or item.get("Flight number list")
            or item.get("flightNumberList")
            or item.get("flightNumbers")
            or item.get("flights")
            or []
        )
        if isinstance(flight_nos, dict):
            flight_nos = [flight_nos]
        # Fallback: flight info may be directly on the item
        if not flight_nos and (item.get("No") or item.get("FlightNo") or item.get("Airline")):
            flight_nos = [item]

        parsed = []
        for fn in flight_nos:
            if not isinstance(fn, dict):
                continue
            flight_no = self._get_str(
                fn, "No", "no", "FlightNo", "flightNo", "number", "flight_number"
            )
            airline = self._get_str(fn, "Airline", "airline", "carrier", "Carrier")
            if flight_no or airline:
                parsed.append(
                    RawFlight(
                        origin=origin,
                        destination=destination,
                        flight_no=flight_no or "",
                        airline=airline or "",
                        scheduled_time=time_str,
                        status=status,
                        date=datetime.strptime(date_str, "%Y-%m-%d").date(),
                        gate=gate,
                        terminal=terminal,
                    )
                )

        if not parsed and (origin or destination):
            parsed.append(
                RawFlight(
                    origin=origin or "",
                    destination=destination or "",
                    flight_no="",
                    airline="",
                    scheduled_time=time_str,
                    status=status,
                    date=datetime.strptime(date_str, "%Y-%m-%d").date(),
                    gate=gate,
                    terminal=terminal,
                )
            )

        return parsed

    def _get_str(self, d: dict, *keys: str) -> Optional[str]:
        for k in keys:
            v = d.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return None

    def _get_str_or_first(self, d: dict, *keys: str) -> Optional[str]:
        """Get string value, or first element if value is a non-empty list."""
        for k in keys:
            v = d.get(k)
            if v is not None:
                if isinstance(v, list) and len(v) > 0:
                    return str(v[0]).strip() if v[0] else None
                s = str(v).strip()
                if s:
                    return s
        return None

    def raw_to_flight(self, raw: RawFlight) -> Flight:
        """Convert RawFlight to normalized Flight."""
        dt = None
        if raw.scheduled_time:
            try:
                dt = datetime.strptime(
                    f"{raw.date.isoformat()} {raw.scheduled_time}",
                    "%Y-%m-%d %H:%M",
                )
            except ValueError:
                try:
                    dt = datetime.strptime(
                        f"{raw.date.isoformat()} {raw.scheduled_time}",
                        "%Y-%m-%d %H:%M:%S",
                    )
                except ValueError:
                    pass

        return Flight(
            origin=raw.origin,
            destination=raw.destination,
            flight_no=raw.flight_no,
            airline=raw.airline,
            scheduled_time=dt,
            status=raw.status,
            date=raw.date,
            gate=raw.gate,
            terminal=raw.terminal,
        )

    @property
    def supported_airports(self) -> Set[str]:
        """HK Airport API only covers flights touching HKG."""
        return {HKG}
