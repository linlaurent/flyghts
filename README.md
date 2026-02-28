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
```

Using pip:

```bash
pip install -e .
```

### Dump Script

Dump all flights from or to Hong Kong for a date or date range. Passenger and cargo flights are included by default. The API provides historical data for approximately the last 90 days only.

Two output modes:
- `--data-dir data/` writes one CSV per date (e.g. `data/2026-02-25.csv`). This is the preferred mode for deployment -- only changed dates are overwritten, keeping git diffs small.
- `-o flights.csv` writes a single CSV, merging with existing data (overlapping dates are replaced).

```bash
# Initial backfill: past 30 days into per-date files
uv run python scripts/dump_hk_flights.py --data-dir data/

# Daily refresh: last 2 days only (used by GitHub Actions)
uv run python scripts/dump_hk_flights.py --days 2 --data-dir data/

# Custom date range
uv run python scripts/dump_hk_flights.py --start 2026-01-01 --end 2026-02-20 --data-dir data/

# Single file mode (legacy)
uv run python scripts/dump_hk_flights.py -o flights.csv

# Passenger only / deduplicate / debug
uv run python scripts/dump_hk_flights.py --no-cargo --data-dir data/
uv run python scripts/dump_hk_flights.py --deduplicate --data-dir data/
uv run python scripts/dump_hk_flights.py --debug
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

### Streamlit Dashboard

Interactive dashboard with top airlines, top destinations (airport/city/country), flight flow map (with multi-airline overlay), airline deep dive, airline comparison, and route deep dive. Reads from `data/` directory (per-date CSVs) or falls back to `flights.csv`.

```bash
uv run streamlit run streamlit/flight_dashboard.py
```

### Deployment (Streamlit Community Cloud)

1. Push the repo to GitHub (including `data/*.csv` files).
2. Connect to [Streamlit Community Cloud](https://share.streamlit.io) and deploy `streamlit/flight_dashboard.py`.
3. A GitHub Actions workflow (`.github/workflows/update_flights.yml`) runs daily at 02:00 UTC, fetches the last 2 days of flight data, and commits the updated per-date CSVs. Streamlit Cloud auto-redeploys on push.

To trigger a manual refresh, go to Actions > "Update flight data" > Run workflow.

## Data Source

Uses the [Hong Kong International Airport Open API](https://data.gov.hk/en-data/dataset/aahk-team1-flight-info) for historical flight data (updated to previous calendar day).
