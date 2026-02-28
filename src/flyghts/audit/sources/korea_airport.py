"""Incheon International Airport (ICN) flight information API client.

Data source: Korea Open Data Portal (data.go.kr), provider B551177.
Requires a free API key from https://www.data.go.kr/ (set KOREA_DATA_API_KEY env var).

Endpoints:
  Arrivals:   /B551177/StatusOfPassengerFlightsOdp/getPassengerArrivalsOdp
  Departures: /B551177/StatusOfPassengerFlightsDep/getPassengerDepartures

Data window: current day (no historical date parameter on passenger endpoints).
Rate limits: 1,000 req/day (dev), 1,000,000 req/day (operational).
"""

import os
import re
from datetime import date, datetime
from typing import Any, List, Optional, Set

import requests

from flyghts.audit.models import Flight
from flyghts.audit.sources.base import RawFlight
from flyghts.reference.airlines import iata_to_icao

BASE_URL = "http://apis.data.go.kr/B551177"

ARRIVALS_ENDPOINT = f"{BASE_URL}/StatusOfPassengerFlightsOdp/getPassengerArrivalsOdp"
DEPARTURES_ENDPOINT = f"{BASE_URL}/StatusOfPassengerFlightsDep/getPassengerDepartures"

ICN = "ICN"
MAX_ROWS = 1000


class KoreaAirportSource:
    """Flight data source for Incheon International Airport via data.go.kr API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 30,
    ):
        self.api_key = api_key or os.environ.get("KOREA_DATA_API_KEY", "")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError(
                "Korea data API key required. Set KOREA_DATA_API_KEY env var "
                "or pass api_key parameter. Register free at https://www.data.go.kr/"
            )

    def fetch_flights(
        self, flight_date: date, arrival: bool, cargo: bool
    ) -> List[RawFlight]:
        """Fetch flights from Incheon Airport API.

        Note: cargo filtering is not supported by this API — cargo=True returns
        an empty list. The API only provides passenger flight data.
        """
        if cargo:
            return []

        endpoint = ARRIVALS_ENDPOINT if arrival else DEPARTURES_ENDPOINT
        all_items = self._fetch_all_pages(endpoint, flight_date)

        flights: list[RawFlight] = []
        for item in all_items:
            raw = self._parse_item(item, flight_date, arrival)
            if raw:
                flights.append(raw)
        return flights

    def _fetch_all_pages(
        self, endpoint: str, flight_date: date
    ) -> list[dict[str, Any]]:
        """Paginate through API results until all items are fetched."""
        all_items: list[dict[str, Any]] = []
        page = 1
        while True:
            params = {
                "serviceKey": self.api_key,
                "type": "json",
                "numOfRows": str(MAX_ROWS),
                "pageNo": str(page),
                "lang": "E",
            }
            resp = requests.get(endpoint, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()

            body = data.get("response", {}).get("body", {})
            items_wrapper = body.get("items") or []

            if isinstance(items_wrapper, dict):
                items = items_wrapper.get("item", [])
            elif isinstance(items_wrapper, list):
                items = items_wrapper
            else:
                items = []

            if isinstance(items, dict):
                items = [items]

            if not items:
                break

            all_items.extend(items)

            total_count = int(body.get("totalCount", 0))
            if len(all_items) >= total_count:
                break
            page += 1

        return all_items

    def _parse_item(
        self, item: dict[str, Any], flight_date: date, arrival: bool
    ) -> Optional[RawFlight]:
        """Parse a single flight item from the API response."""
        flight_id = str(item.get("flightId", "")).strip()
        if not flight_id:
            return None

        airline_iata = self._extract_airline_code(flight_id)
        airline_icao = iata_to_icao(airline_iata) or airline_iata

        airport_code = str(item.get("cityCode", "")).strip()
        if not airport_code:
            airport_code = str(item.get("airport", "")).strip()

        if arrival:
            origin = airport_code
            destination = ICN
        else:
            origin = ICN
            destination = airport_code

        sched_time = str(item.get("scheduleDateTime", "")).strip()
        est_time = str(item.get("estimatedDateTime", "")).strip()

        scheduled_dt_str = None
        if sched_time and len(sched_time) >= 4:
            scheduled_dt_str = f"{sched_time[:2]}:{sched_time[2:4]}"

        status = self._build_status(item, est_time)
        gate = str(item.get("gatenumber", "")).strip() or None
        terminal = str(item.get("terminalid", "")).strip() or None

        codeshare = str(item.get("codeshare", "")).strip()
        master_flight = str(item.get("masterflightid", "")).strip()
        op_flight_no = ""
        op_airline = ""
        if codeshare and master_flight:
            op_flight_no = master_flight
            op_airline_iata = self._extract_airline_code(master_flight)
            op_airline = iata_to_icao(op_airline_iata) or op_airline_iata
        else:
            op_flight_no = flight_id
            op_airline = airline_icao

        return RawFlight(
            origin=origin,
            destination=destination,
            flight_no=flight_id,
            airline=airline_icao,
            scheduled_time=scheduled_dt_str,
            status=status,
            date=flight_date,
            gate=gate,
            terminal=terminal,
            cargo=False,
            operating_flight_no=op_flight_no,
            operating_airline=op_airline,
        )

    def _extract_airline_code(self, flight_id: str) -> str:
        """Extract the IATA airline prefix from a flight ID like 'KE094' or 'OZ201'."""
        match = re.match(r"^([A-Z]{2})\d", flight_id)
        if match:
            return match.group(1)
        match = re.match(r"^([A-Z0-9]{2})\d", flight_id)
        if match:
            return match.group(1)
        return flight_id[:2] if len(flight_id) >= 2 else flight_id

    def _build_status(self, item: dict[str, Any], est_time: str) -> Optional[str]:
        """Build a human-readable status string from API fields."""
        remark = str(item.get("remark", "")).strip()
        if remark:
            return remark
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
            cargo=raw.cargo,
            operating_flight_no=raw.operating_flight_no,
            operating_airline=raw.operating_airline,
        )

    @property
    def supported_airports(self) -> Set[str]:
        """ICN Airport API only covers flights touching Incheon."""
        return {ICN}
