# Flyghts

Python package for flight traffic data analysis and auditing.

## Flight Audit

Query and analyze flight traffic between routes (e.g. Hong Kong ↔ Taipei).

### Installation

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
# Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

### Tests

```bash
uv run pytest tests/ -v
# or with the project venv: pytest tests/ -v
```

Using pip:

```bash
pip install -e .
```

### CLI

```bash
# Single day
flyghts-audit --route HKG-TPE --date 2025-02-17

# Past 7 days
flyghts-audit --route HKG-TPE --days 7

# With statistics
flyghts-audit --route HKG-TPE --date 2025-02-17 --stats

# Export to CSV
flyghts-audit --route HKG-TPE --days 7 --output flights.csv
```

### Python API

```python
from datetime import date
from flyghts.audit import AuditService
from flyghts.audit.models import DateFilter, RouteFilter

service = AuditService()
route = RouteFilter.from_route_string("HKG-TPE")
date_filter = DateFilter.single(date(2025, 2, 17))
result = service.query(route, date_filter)
stats = service.statistics(result.flights)
```

### Marimo GUI

```bash
marimo edit marimo/flight_audit.py
# or
marimo run marimo/flight_audit.py
```

## Data Source

Uses the [Hong Kong International Airport Open API](https://data.gov.hk/en-data/dataset/aahk-team1-flight-info) for historical flight data (updated to previous calendar day).
