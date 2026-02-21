"""Statistics computation for flight audit."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

import pandas as pd

from flyghts.audit.models import Flight


@dataclass
class FlightStats:
    """Container for flight statistics."""

    total_flights: int = 0
    by_airline: Dict[str, int] = field(default_factory=dict)
    by_date: Dict[str, int] = field(default_factory=dict)
    by_route: Dict[str, int] = field(default_factory=dict)
    by_hour: Dict[int, int] = field(default_factory=dict)
    status_summary: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_flights": self.total_flights,
            "by_airline": self.by_airline,
            "by_date": self.by_date,
            "by_route": self.by_route,
            "by_hour": self.by_hour,
            "status_summary": self.status_summary,
        }

    def airline_dataframe(self) -> pd.DataFrame:
        """Return by_airline as DataFrame."""
        if not self.by_airline:
            return pd.DataFrame(columns=["airline", "count"])
        return pd.DataFrame(
            [{"airline": k, "count": v} for k, v in sorted(self.by_airline.items())]
        )

    def hourly_dataframe(self) -> pd.DataFrame:
        """Return by_hour as DataFrame (flights per hour)."""
        if not self.by_hour:
            return pd.DataFrame(columns=["hour", "count"])
        return pd.DataFrame(
            [{"hour": h, "count": c} for h, c in sorted(self.by_hour.items())]
        )


def compute_stats(flights: List[Flight]) -> FlightStats:
    """Compute statistics from a list of flights."""
    stats = FlightStats()

    if not flights:
        return stats

    stats.total_flights = len(flights)

    for f in flights:
        # By airline
        if f.airline:
            stats.by_airline[f.airline] = stats.by_airline.get(f.airline, 0) + 1

        # By date
        date_key = f.date.isoformat()
        stats.by_date[date_key] = stats.by_date.get(date_key, 0) + 1

        # By route
        route = f.route()
        stats.by_route[route] = stats.by_route.get(route, 0) + 1

        # By hour
        if f.scheduled_time:
            h = f.scheduled_time.hour
            stats.by_hour[h] = stats.by_hour.get(h, 0) + 1

        # Status summary
        status = (f.status or "Unknown").strip() or "Unknown"
        stats.status_summary[status] = stats.status_summary.get(status, 0) + 1

    return stats
