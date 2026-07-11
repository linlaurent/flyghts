"""Flight dashboard shared modules."""

from .charts import (
    _complete_daily_series,
    _daily_date_range,
    _render_overview_flights_per_day,
    _start_flight_count_axis_at_zero,
)
from .components import _render_aggrid, _render_insight_grid
from .config import DATASETS, PROJECT_ROOT
from .context import DashboardContext
from .data import (
    apply_filters,
    build_map_points,
    get_destination_column,
    load_flights,
    parse_delay_minutes,
)
from .formatting import (
    RouteCityKey,
    _airline_label,
    _airport_city_key,
    _airport_province,
    _build_region_route_selection,
    _city_key_display,
    _city_key_label,
    _city_pair_airport_counts,
    _format_insight_table,
    _multi_airport_city_keys_for_iatas,
    _region_key_for_iata,
    _route_label,
)
from .insight_ui import (
    _comparison_period_options,
    _default_current_period_index,
    _filter_df_for_insight_routes,
    _render_insight_chart,
    _render_insight_route_map,
    _slice_period,
)
from .maps import (
    _get_map_layout_opts,
    _map_center_zoom_from_coords,
    _render_flight_map,
    _render_network_map,
    _render_region_airport_map,
    _render_route_top_airports_tab,
)
from .sidebar import build_dashboard_context

__all__ = [
    "DATASETS",
    "PROJECT_ROOT",
    "DashboardContext",
    "RouteCityKey",
    "_airline_label",
    "_airport_city_key",
    "_airport_province",
    "_build_region_route_selection",
    "_city_key_display",
    "_city_key_label",
    "_city_pair_airport_counts",
    "_comparison_period_options",
    "_complete_daily_series",
    "_daily_date_range",
    "_default_current_period_index",
    "_filter_df_for_insight_routes",
    "_format_insight_table",
    "_get_map_layout_opts",
    "_map_center_zoom_from_coords",
    "_multi_airport_city_keys_for_iatas",
    "_region_key_for_iata",
    "_render_aggrid",
    "_render_flight_map",
    "_render_insight_chart",
    "_render_insight_grid",
    "_render_insight_route_map",
    "_render_network_map",
    "_render_overview_flights_per_day",
    "_render_region_airport_map",
    "_render_route_top_airports_tab",
    "_route_label",
    "_slice_period",
    "_start_flight_count_axis_at_zero",
    "apply_filters",
    "build_dashboard_context",
    "build_map_points",
    "get_destination_column",
    "load_flights",
    "parse_delay_minutes",
]
