"""Airline alliance membership lookup (OpenTravelData, CC-BY 4.0).

Membership is point-in-time: callers pass as_of (defaults to today UTC).
Never inferred from marketing vs operating code-shares.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib import resources
from typing import Optional

import json

_alliances_by_iata: Optional[dict[str, list[dict]]] = None
_alliances_by_icao: Optional[dict[str, list[dict]]] = None


@dataclass(frozen=True)
class AllianceInfo:
    """Alliance membership spell for an airline."""

    alliance: str
    alliance_type: str
    iata: str = ""
    icao: str = ""
    name: str = ""
    from_date: Optional[date] = None
    to_date: Optional[date] = None

    @property
    def is_member(self) -> bool:
        return self.alliance_type == "member"


def _parse_iso_date(value: object) -> Optional[date]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _normalize_interval_lists(
    raw: dict,
) -> dict[str, list[dict]]:
    """Accept legacy single-dict values or interval lists."""
    out: dict[str, list[dict]] = {}
    for key, value in raw.items():
        if isinstance(value, list):
            out[key] = value
        elif isinstance(value, dict):
            out[key] = [value]
    return out


def _load_alliances() -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    global _alliances_by_iata, _alliances_by_icao
    if _alliances_by_iata is None or _alliances_by_icao is None:
        try:
            data_path = resources.files("flyghts.reference.data").joinpath(
                "alliances.json"
            )
            with data_path.open() as f:
                payload = json.load(f)
            _alliances_by_iata = _normalize_interval_lists(payload.get("by_iata") or {})
            _alliances_by_icao = _normalize_interval_lists(payload.get("by_icao") or {})
        except (FileNotFoundError, json.JSONDecodeError, AttributeError):
            _alliances_by_iata = {}
            _alliances_by_icao = {}
    return _alliances_by_iata, _alliances_by_icao


def _row_to_info(row: dict) -> AllianceInfo:
    return AllianceInfo(
        alliance=row.get("alliance", ""),
        alliance_type=row.get("alliance_type", ""),
        iata=row.get("iata", "") or "",
        icao=row.get("icao", "") or "",
        name=row.get("name", "") or "",
        from_date=_parse_iso_date(row.get("from_date")),
        to_date=_parse_iso_date(row.get("to_date")),
    )


def _interval_covers(row: dict, as_of: date) -> bool:
    start = _parse_iso_date(row.get("from_date"))
    end = _parse_iso_date(row.get("to_date"))
    if start is not None and as_of < start:
        return False
    if end is not None and as_of > end:
        return False
    # Legacy current-only rows without dates: treat as always in effect
    return True


def _pick_interval(
    intervals: list[dict], *, as_of: date, members_only: bool
) -> Optional[AllianceInfo]:
    matches = [row for row in intervals if _interval_covers(row, as_of)]
    if members_only:
        matches = [row for row in matches if row.get("alliance_type") == "member"]
    if not matches:
        return None
    members = [row for row in matches if row.get("alliance_type") == "member"]
    chosen = members[0] if members else matches[0]
    return _row_to_info(chosen)


def _default_as_of(as_of: Optional[date]) -> date:
    if as_of is not None:
        return as_of
    return datetime.now(timezone.utc).date()


def get_alliance(
    icao: str, *, as_of: Optional[date] = None, members_only: bool = True
) -> Optional[AllianceInfo]:
    """Look up alliance by ICAO as of a date (default: today UTC). Members only by default."""
    if not icao:
        return None
    icao = icao.upper().strip()
    _, by_icao = _load_alliances()
    intervals = by_icao.get(icao) or []
    if not intervals:
        return None
    return _pick_interval(
        intervals, as_of=_default_as_of(as_of), members_only=members_only
    )


def get_alliance_by_iata(
    iata: str, *, as_of: Optional[date] = None, members_only: bool = True
) -> Optional[AllianceInfo]:
    """Look up alliance by IATA as of a date (default: today UTC). Members only by default."""
    if not iata:
        return None
    iata = iata.upper().strip()
    by_iata, _ = _load_alliances()
    intervals = by_iata.get(iata) or []
    if not intervals:
        return None
    return _pick_interval(
        intervals, as_of=_default_as_of(as_of), members_only=members_only
    )


def list_alliances(*, members_only: bool = False) -> list[AllianceInfo]:
    """Return all membership intervals (one row per spell), sorted."""
    _, by_icao = _load_alliances()
    results: list[AllianceInfo] = []
    for intervals in by_icao.values():
        for row in intervals:
            info = _row_to_info(row)
            if members_only and not info.is_member:
                continue
            results.append(info)
    results.sort(
        key=lambda a: (
            a.alliance,
            a.icao or a.iata,
            a.from_date or date.min,
            a.to_date or date.max,
        )
    )
    return results
