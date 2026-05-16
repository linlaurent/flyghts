#!/bin/bash
cd "$(dirname "$0")"
exec uv run streamlit run streamlit/flight_dashboard.py
