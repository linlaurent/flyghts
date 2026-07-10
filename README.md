# Flyghts

Python package for multi-source flight traffic data analysis and auditing.

## Data Sources

Flight data is organized by source under `data/`:

| Source | Directory | Coverage | API | Auth |
|--------|-----------|----------|-----|------|
| **Hong Kong (HKG)** | `data/hkg/` | HKG departures & arrivals (passenger + cargo) | [HK Airport Open API](https://data.gov.hk/en-data/dataset/aahk-team1-flight-info) | None |
| **Korea (ICN)** | `data/korea/` | Incheon departures & arrivals (passenger) | [data.go.kr B551177](https://www.data.go.kr/en/data/15095093/openapi.do) | Free API key |
| **US Domestic** | `data/us/` | All US domestic flights (monthly Parquet) | [BTS TranStats](https://www.transtats.bts.gov/) | None |

## Installation

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
# Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

Using pip:

```bash
pip install -e .
```

### Tests

```bash
uv run pytest tests/ -v
```

## Dump Scripts

### Hong Kong (HKG)

Dump all flights from/to Hong Kong. The API provides ~90 days of history.

```bash
# Initial backfill: past 30 days
uv run python scripts/dump_hk_flights.py --data-dir data/hkg/

# Daily refresh (used by GitHub Actions)
uv run python scripts/dump_hk_flights.py --days 2 --data-dir data/hkg/

# Custom date range
uv run python scripts/dump_hk_flights.py --start 2026-01-01 --end 2026-02-20 --data-dir data/hkg/

# Passenger only / deduplicate / debug
uv run python scripts/dump_hk_flights.py --no-cargo --data-dir data/hkg/
uv run python scripts/dump_hk_flights.py --deduplicate --data-dir data/hkg/
uv run python scripts/dump_hk_flights.py --debug
```

### Korea (Incheon ICN)

Dump passenger flights from/to Incheon. Current-day data only -- run daily to accumulate.
Requires `KOREA_DATA_API_KEY` env var (free registration at [data.go.kr](https://www.data.go.kr/)).

```bash
export KOREA_DATA_API_KEY="your-key-here"
uv run python scripts/dump_korea_flights.py --data-dir data/korea/
uv run python scripts/dump_korea_flights.py --debug
```

### US Domestic (BTS)

Download US domestic on-time performance data from the Bureau of Transportation Statistics.
No API key needed. Data is ~2 months behind current date. Writes one Parquet file per month
(e.g. `data/us/2025-01.parquet`).

```bash
# Download most recent available month
uv run python scripts/dump_us_flights.py --latest --data-dir data/us/

# Download a specific month
uv run python scripts/dump_us_flights.py --year 2024 --month 12 --data-dir data/us/

# Download an entire year
uv run python scripts/dump_us_flights.py --year 2024 --data-dir data/us/

# Migrate existing daily CSVs to monthly Parquet (one-time)
uv run python scripts/migrate_us_csv_to_parquet.py
```

### Validate Reference Data

Check flight data files for airline/airport codes missing from the reference data:

```bash
# Validate all sources
uv run python scripts/validate_reference_data.py

# Validate a specific source
uv run python scripts/validate_reference_data.py --data-dir data/korea/
uv run python scripts/validate_reference_data.py --data-dir data/us/
```

## Flight Audit

Query and analyze flight traffic between routes (e.g. Hong Kong <-> Taipei).

### CLI

```bash
flyghts-audit --route HKG-TPE --date 2025-02-17
flyghts-audit --route HKG-TPE --days 7 --stats
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

### Streamlit Dashboard

Interactive dashboard for HKG flight analysis. Reads from `data/hkg/`.

```bash
uv run streamlit run streamlit/flight_dashboard.py
```

## Deployment (Streamlit Community Cloud)

1. Push the repo to GitHub (including `data/hkg/*.csv` files).
2. Connect to [Streamlit Community Cloud](https://share.streamlit.io) and deploy `streamlit/flight_dashboard.py`.
3. A GitHub Actions workflow runs daily at 02:00 HKT, fetches the last 2 days of HKG flight data, and commits the updated CSVs.

To trigger a manual refresh, go to Actions > "Update flight data" > Run workflow.
