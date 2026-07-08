"""Regression tests for dashboard chart conventions."""

from pathlib import Path
import re


DASHBOARD_PATH = (
    Path(__file__).resolve().parent.parent / "streamlit" / "flight_dashboard.py"
)


def _dashboard_source() -> str:
    return DASHBOARD_PATH.read_text()


def test_flight_count_plotly_axes_start_at_zero() -> None:
    source = _dashboard_source()
    plot_calls = list(re.finditer(r"st\.plotly_chart\(\s*(\w+)", source))
    chart_assignments = list(
        re.finditer(
            r"(?m)^(\s*)(\w+)\s*=\s*(?:px\.(?:bar|line|histogram)|go\.Figure)\(", source
        )
    )
    count_axis_patterns = (
        'x="Flights"',
        'y="Flights"',
        'name="Flights"',
        'title="Number of flights"',
        '"count": "Flights"',
        '"Avg": "Avg flights per day"',
    )
    missing: list[str] = []

    for plot_call in plot_calls:
        fig_name = plot_call.group(1)
        assignment = next(
            (
                match
                for match in reversed(chart_assignments)
                if match.group(2) == fig_name and match.start() < plot_call.start()
            ),
            None,
        )
        if assignment is None:
            continue

        chart_block = source[assignment.start() : plot_call.start()]
        has_flight_count_axis = any(
            pattern in chart_block for pattern in count_axis_patterns
        )
        has_zero_baseline = bool(
            re.search(
                rf"_start_flight_count_axis_at_zero\(\s*{fig_name},\s*\"[xy]\"\s*\)",
                chart_block,
            )
        )
        if has_flight_count_axis and not has_zero_baseline:
            line_no = source[: assignment.start()].count("\n") + 1
            missing.append(f"{fig_name} at line {line_no}")

    assert missing == []


def test_insight_flight_count_charts_use_zero_baseline_rule() -> None:
    source = _dashboard_source()

    assert '_start_flight_count_axis_at_zero(fig, "x")' in source
    assert '"Previous flights"' in source
    assert '"Current flights"' in source
