"""Regression tests for dashboard chart conventions."""

from pathlib import Path
import re


DASHBOARD_PATH = (
    Path(__file__).resolve().parent.parent / "streamlit" / "flight_dashboard.py"
)
DASHBOARD_RULE_PATH = (
    Path(__file__).resolve().parent.parent
    / ".cursor"
    / "rules"
    / "streamlit-dashboard.mdc"
)


def _dashboard_source() -> str:
    return DASHBOARD_PATH.read_text()


def _dashboard_rule_source() -> str:
    return DASHBOARD_RULE_PATH.read_text()


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


def test_route_arc_count_uses_top_n_ranking_control() -> None:
    source = _dashboard_source()

    assert "Top route arcs to draw" not in source
    assert "top_routes_n=top_n" in source
    assert "top_arcs_n=top_n" in source


def test_route_deep_dive_supports_city_mode() -> None:
    source = _dashboard_source()

    assert 'route_mode_options = ["By airport", "By city"]' in source
    assert 'route_by_city = route_mode == "By city"' in source
    assert "route_str_to_city_keys" in source
    assert "Search routes by city, country, or airport code" in source
    assert "Only cities with multiple airports" in source
    assert "route_dive_multi_airport_only" in source
    assert "Airport comparison" in source
    assert "Top airline contributions by airport" in source
    assert "Share of city flights per day by airport" in source


def test_insight_frequency_changes_can_use_percent_metric() -> None:
    source = _dashboard_source()

    assert "Frequency change metric" in source
    assert 'options=["Change/day", "Change (%)"]' in source
    assert '"percent_change"' in source
    assert "frequency_value_col" in source


def test_insight_frequency_changes_keep_drops_left_of_increases() -> None:
    source = _dashboard_source()
    frequency_tab = source.split("with insight_tabs[3]:", maxsplit=1)[1].split(
        "# ══════════════════════════════════════════════════════════════════════",
        maxsplit=1,
    )[0]

    ordered_pairs = [
        (
            "chart_frequency_drops_left, chart_frequency_increases_right = st.columns(2)",
            "with chart_frequency_drops_left:",
            "with chart_frequency_increases_right:",
        ),
        (
            "map_frequency_drops_left, map_frequency_increases_right = st.columns(2)",
            "with map_frequency_drops_left:",
            "with map_frequency_increases_right:",
        ),
        (
            "table_frequency_drops_left, table_frequency_increases_right = st.columns(2)",
            "with table_frequency_drops_left:",
            "with table_frequency_increases_right:",
        ),
    ]

    for columns_call, drops_block, increases_block in ordered_pairs:
        assert columns_call in frequency_tab
        assert frequency_tab.index(drops_block) < frequency_tab.index(increases_block)


def test_streamlit_dashboard_rule_documents_frequency_layout() -> None:
    rule = _dashboard_rule_source()

    assert "globs: streamlit/**/*.py" in rule
    assert "Frequency-change comparisons place drops on the left" in rule
    assert "increases on the right" in rule


def test_focus_airport_maps_center_on_focus_airport() -> None:
    source = _dashboard_source()

    assert (
        "fig_map.update_geos(**_get_map_geo_opts(geo_scope, (focus_lat, focus_lon)))"
        in source
    )
    assert 'opts["center"] = dict(lat=center[0], lon=center[1])' in source


def _call_blocks(source: str, call_name: str) -> list[str]:
    blocks: list[str] = []
    pos = 0
    while True:
        start = source.find(call_name, pos)
        if start == -1:
            return blocks
        paren = source.find("(", start)
        depth = 0
        end = None
        for idx in range(paren, len(source)):
            if source[idx] == "(":
                depth += 1
            elif source[idx] == ")":
                depth -= 1
                if depth == 0:
                    end = idx
                    break
        assert end is not None
        blocks.append(source[start : end + 1])
        pos = end + 1


def test_all_line_charts_hide_markers() -> None:
    source = _dashboard_source()

    for block in _call_blocks(source, "px.line"):
        assert "markers=True" not in block

    for block in _call_blocks(source, "go.Scatter("):
        assert 'mode="lines+markers"' not in block
        assert 'mode="lines"' in block


def test_date_line_charts_complete_daily_series() -> None:
    source = _dashboard_source()

    assert "def _daily_date_range(" in source
    assert "def _complete_daily_series(" in source
    assert source.count("_complete_daily_series(") >= 14
