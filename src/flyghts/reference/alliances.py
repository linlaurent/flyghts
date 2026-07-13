"""Airline alliance membership lookup (OpenTravelData, CC-BY 4.0)."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Optional

import json

_alliances_by_iata: Optional[dict[str, dict]] = None
_alliances_by_icao: Optional[dict[str, dict]] = None


@dataclass(frozen=True)
class AllianceInfo:
    """Alliance membership for an airline."""

    alliance: str
    alliance_type: str
    iata: str = ""
    icao: str = ""
    name: str = ""

    @property
    def is_member(self) -> bool:
        return self.alliance_type == "member"


def _load_alliances() -> tuple[dict[str, dict], dict[str, dict]]:
    global _alliances_by_iata, _alliances_by_icao
    if _alliances_by_iata is None or _alliances_by_icao is None:
        try:
            data_path = resources.files("flyghts.reference.data").joinpath(
                "alliances.json"
            )
            with data_path.open() as f:
                payload = json.load(f)
            _alliances_by_iata = payload.get("by_iata") or {}
            _alliances_by_icao = payload.get("by_icao") or {}
        except (FileNotFoundError, json.JSONDecodeError, AttributeError):
            _alliances_by_iata = {}
            _alliances_by_icao = {}
    return _alliances_by_iata, _alliances_by_icao


def _row_to_info(row: dict) -> AllianceInfo:
    return AllianceInfo(
        alliance=row.get("alliance", ""),
        alliance_type=row.get("alliance_type", ""),
        iata=row.get("iata", ""),
        icao=row.get("icao", ""),
        name=row.get("name", ""),
    )


def get_alliance(icao: str, *, members_only: bool = True) -> Optional[AllianceInfo]:
    """Look up alliance by ICAO. Default returns full members only."""
    if not icao:
        return None
    icao = icao.upper().strip()
    _, by_icao = _load_alliances()
    row = by_icao.get(icao)
    if not row:
        return None
    info = _row_to_info(row)
    if members_only and not info.is_member:
        return None
    return info


def get_alliance_by_iata(
    iata: str, *, members_only: bool = True
) -> Optional[AllianceInfo]:
    """Look up alliance by IATA. Default returns full members only."""
    if not iata:
        return None
    iata = iata.upper().strip()
    by_iata, _ = _load_alliances()
    row = by_iata.get(iata)
    if not row:
        return None
    info = _row_to_info(row)
    if members_only and not info.is_member:
        return None
    return info


def list_alliances(*, members_only: bool = False) -> list[AllianceInfo]:
    """Return alliance memberships from the ICAO index, sorted by alliance then ICAO."""
    _, by_icao = _load_alliances()
    results: list[AllianceInfo] = []
    for row in by_icao.values():
        info = _row_to_info(row)
        if members_only and not info.is_member:
            continue
        results.append(info)
    results.sort(key=lambda a: (a.alliance, a.icao or a.iata))
    return results
