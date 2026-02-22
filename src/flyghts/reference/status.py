"""Parse flight status strings."""

import re
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class ParsedStatus:
    """Parsed flight status."""

    status_type: Literal["departed", "arrived", "at_gate", "cancelled", "delayed", "unknown"]
    actual_time: Optional[str]  # "HH:MM"
    actual_date: Optional[str]  # "YYYY-MM-DD"


# (Dep|Arr|At gate) HH:MM or HH:MM (DD/MM/YYYY)
_STATUS_RE = re.compile(
    r"^(Dep|Arr|At gate)\s+(\d{1,2}:\d{2})(?:\s+\((\d{1,2})/(\d{1,2})/(\d{4})\))?\s*$",
    re.IGNORECASE,
)
_TYPE_MAP = {
    "dep": "departed",
    "arr": "arrived",
    "at gate": "at_gate",
}


def parse_status(status: Optional[str]) -> ParsedStatus:
    """Parse a raw status string into structured fields."""
    if not status or not isinstance(status, str):
        return ParsedStatus(status_type="unknown", actual_time=None, actual_date=None)

    s = status.strip()
    if not s:
        return ParsedStatus(status_type="unknown", actual_time=None, actual_date=None)

    # Literal matches
    if s.lower() == "cancelled":
        return ParsedStatus(status_type="cancelled", actual_time=None, actual_date=None)
    if s.lower() == "delayed":
        return ParsedStatus(status_type="delayed", actual_time=None, actual_date=None)

    # Regex for Dep/Arr/At gate + time [+ date]
    m = _STATUS_RE.match(s)
    if m:
        prefix, time_str, dd, mm, yyyy = m.groups()
        prefix_lower = prefix.strip().lower()
        status_type = _TYPE_MAP.get(prefix_lower, "unknown")
        actual_date = None
        if dd and mm and yyyy:
            try:
                d, mo, y = int(dd), int(mm), int(yyyy)
                actual_date = f"{y:04d}-{mo:02d}-{d:02d}"
            except ValueError:
                pass
        return ParsedStatus(
            status_type=status_type,
            actual_time=time_str,
            actual_date=actual_date,
        )

    return ParsedStatus(status_type="unknown", actual_time=None, actual_date=None)
