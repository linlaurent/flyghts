"""Dashboard configuration constants."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DATASETS: dict[str, dict] = {
    "HKG": {"dir": "hkg", "scope": "world", "default_airport": "HKG", "format": "csv"},
    "US Domestic": {
        "dir": "us",
        "scope": "usa",
        "default_airport": None,
        "format": "parquet",
    },
}



