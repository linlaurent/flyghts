"""
Flight Dashboard - Analyze flight data across multiple datasets.

Supports HKG (Hong Kong International Airport) and US Domestic flight data.
Reads per-date CSVs from data/hkg/ and monthly Parquet files from data/us/.

Features:
- Dataset selector (HKG / US Domestic)
- Two modes for US Domestic:
    - Focus airport: hub-centric view with direction filter and spoke-map
    - Global network: network-wide statistics (top routes, busiest airports,
      network map with airport bubbles + route arcs) and no focus constraint
- Top airlines/destinations, interactive map with multi-airline overlay
- Airline deep dive (top O-D pairs in global mode) and airline comparison
- Route deep dive, delay analysis (US)

Run with: uv run streamlit run streamlit/flight_dashboard.py
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder

from flyghts.insights import (
    DEFAULT_COMPANY_AIRLINE_COL,
    DEFAULT_MIN_ABSOLUTE_CHANGE_PER_DAY,
    DEFAULT_MIN_PERCENT_CHANGE,
    DEFAULT_MIN_PREVIOUS_FLIGHTS,
    MARKETING_AIRLINE_COL,
    available_period_labels,
    compare_periods,
)
from flyghts.reference import get_airline, get_airport

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATASETS: dict[str, dict] = {
    "HKG": {"dir": "hkg", "scope": "world", "default_airport": "HKG", "format": "csv"},
    "US Domestic": {
        "dir": "us",
        "scope": "usa",
        "default_airport": None,
        "format": "parquet",
    },
}

_DELAY_RE = re.compile(r"\(\+(\d+)min\)")


@st.cache_data
def load_flights(dataset_key: str) -> pd.DataFrame:
    """Load flight data for the given dataset (CSV or Parquet)."""
    dataset = DATASETS[dataset_key]
    data_dir = PROJECT_ROOT / "data" / dataset["dir"]
    file_format = dataset.get("format", "csv")

    if file_format == "parquet":
        files = sorted(data_dir.glob("*.parquet")) if data_dir.exists() else []
        if not files:
            st.error(
                f"No flight data found for {dataset_key}. Run the dump script first."
            )
            st.stop()
        dfs = [pd.read_parquet(f) for f in files]
    else:
        files = sorted(data_dir.glob("*.csv")) if data_dir.exists() else []
        if not files:
            st.error(
                f"No flight data found for {dataset_key}. Run the dump script first."
            )
            st.stop()
        dfs = [pd.read_csv(f) for f in files]

    df = pd.concat(dfs, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    if "cargo" in df.columns:

        def _to_bool(x):
            if pd.isna(x):
                return False
            if isinstance(x, bool):
                return x
            return str(x).lower() in ("true", "1", "yes")

        df["cargo"] = df["cargo"].apply(_to_bool)
    return df


def apply_filters(
    df: pd.DataFrame,
    direction: str,
    focus_airport: str | None,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    cargo_filter: str | None = None,
    operating_only: bool = False,
) -> pd.DataFrame:
    """Filter by direction relative to focus airport, date range, cargo, and operating-only.

    When focus_airport is None (global mode) no directional filter is applied.
    """
    mask = (df["date"] >= start_date) & (df["date"] <= end_date)
    if focus_airport:
        if direction == "Departures":
            mask = mask & (df["origin"] == focus_airport)
        elif direction == "Arrivals":
            mask = mask & (df["destination"] == focus_airport)
        else:
            mask = mask & (
                (df["origin"] == focus_airport) | (df["destination"] == focus_airport)
            )
    if cargo_filter and "cargo" in df.columns:
        if cargo_filter == "Passenger only":
            mask = mask & (~df["cargo"])
        elif cargo_filter == "Cargo only":
            mask = mask & df["cargo"]
    if operating_only and "operating_airline" in df.columns:
        mask = mask & (df["airline"] == df["operating_airline"])
    return df[mask]


def get_destination_column(
    df: pd.DataFrame, direction: str, focus_airport: str | None
) -> pd.Series:
    """Return the 'other end' airport codes relative to the focus airport.

    When focus_airport is None (global mode) returns the destination column directly.
    """
    if focus_airport is None:
        return df["destination"]
    if direction == "Departures":
        return df["destination"]
    if direction == "Arrivals":
        return df["origin"]
    origins = df[df["origin"] != focus_airport]["origin"]
    dests = df[df["destination"] != focus_airport]["destination"]
    return pd.concat([origins, dests])


def parse_delay_minutes(status: str) -> int | None:
    """Extract delay minutes from US-format status strings.

    Returns 0 for on-time arrivals, positive int for late arrivals,
    None for cancelled/diverted/unknown.
    """
    if not isinstance(status, str):
        return None
    s = status.strip()
    if s.startswith("Cancelled") or s.startswith("Diverted"):
        return None
    m = _DELAY_RE.search(s)
    if m:
        return int(m.group(1))
    if s.startswith("Arr ") or s.startswith("Dep "):
        return 0
    return None


def build_map_points(dest_counts: "pd.Series", by_country: bool) -> list[dict]:
    """Build map point data from destination IATA counts."""
    points: list[dict] = []
    if by_country:
        country_agg: dict[str, list[tuple[float, float, int]]] = {}
        for iata, count in dest_counts.items():
            info = get_airport(iata)
            if not info or (info.latitude == 0 and info.longitude == 0):
                continue
            country = info.country or iata
            if country not in country_agg:
                country_agg[country] = []
            country_agg[country].append((info.latitude, info.longitude, count))
        for country, pts in country_agg.items():
            total = sum(p[2] for p in pts)
            if total == 0:
                continue
            lat = sum(p[0] * p[2] for p in pts) / total
            lon = sum(p[1] * p[2] for p in pts) / total
            points.append(
                {
                    "iata": country,
                    "lat": lat,
                    "lon": lon,
                    "count": total,
                    "label": f"{country}: {total:,} flights",
                }
            )
    else:
        for iata, count in dest_counts.items():
            info = get_airport(iata)
            if info and (info.latitude != 0 or info.longitude != 0):
                points.append(
                    {
                        "iata": iata,
                        "lat": info.latitude,
                        "lon": info.longitude,
                        "count": count,
                        "label": f"{iata} ({info.city or '?'}, {info.country or '?'}): {count:,}",
                    }
                )
    return points


def _get_map_geo_opts(
    scope: str = "world", center: tuple[float, float] | None = None
) -> dict:
    """Return geo layout options parameterized by scope."""
    opts = dict(
        showland=True,
        coastlinewidth=0.5,
        landcolor="rgb(243,243,243)",
        showcountries=True,
        countrycolor="rgba(150,150,150,0.6)",
        countrywidth=0.5,
    )
    if scope == "usa":
        opts["scope"] = "north america"
        if center is None:
            opts["lataxis"] = dict(range=[17, 72])
            opts["lonaxis"] = dict(range=[-170, -64])
    elif scope == "world":
        opts["scope"] = "world"
        opts["projection_type"] = "natural earth"
    else:
        opts["scope"] = scope
    if center is not None:
        opts["center"] = dict(lat=center[0], lon=center[1])
    return opts


def _start_flight_count_axis_at_zero(fig: go.Figure, axis: str = "y") -> None:
    """Force flight-count axes to include zero as their baseline."""
    if axis == "x":
        fig.update_xaxes(rangemode="tozero")
        return
    if axis == "y":
        fig.update_yaxes(rangemode="tozero")
        return
    layout_axis = f"{axis[0]}axis{axis[1:]}"
    fig.update_layout({layout_axis: {"rangemode": "tozero"}})


def _daily_date_range(start_date, end_date) -> pd.DatetimeIndex:
    """Return the selected date window as a daily DatetimeIndex."""
    return pd.date_range(
        pd.Timestamp(start_date).normalize(),
        pd.Timestamp(end_date).normalize(),
        freq="D",
    )


def _complete_daily_series(
    df: pd.DataFrame,
    *,
    date_col: str,
    value_cols: list[str],
    start_date,
    end_date,
    group_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Fill missing dates in a time series with zero values."""
    date_range = _daily_date_range(start_date, end_date)
    group_cols = group_cols or []
    if df.empty:
        columns = [date_col, *group_cols, *value_cols]
        return pd.DataFrame(columns=columns)

    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col]).dt.normalize()

    if group_cols:
        groups = work[group_cols].drop_duplicates()
        full_index = pd.MultiIndex.from_frame(
            groups.merge(pd.DataFrame({date_col: date_range}), how="cross")[
                [*group_cols, date_col]
            ]
        )
        completed = (
            work.set_index([*group_cols, date_col]).reindex(full_index).reset_index()
        )
    else:
        completed = work.set_index(date_col).reindex(date_range).reset_index()
        completed = completed.rename(columns={"index": date_col})

    for col in value_cols:
        if col in completed.columns:
            completed[col] = completed[col].fillna(0)
    return completed


def _render_flight_map(
    df_map: pd.DataFrame,
    direction: str,
    focus_airport: str,
    focus_lat: float,
    focus_lon: float,
    map_by_country: bool,
    airline_codes: list[str],
    airline_col: str,
    geo_scope: str = "world",
    use_traffic_colors: bool = False,
    top_arcs_n: int | None = None,
) -> None:
    """Render interactive flight map from focus airport.

    When use_traffic_colors=True, spoke arcs use the cool→warm traffic-volume
    color scale regardless of airline (useful for single-airline deep dives).
    When top_arcs_n is set, only the top N destinations by flight count are shown.
    """
    if df_map.empty:
        st.info("No flight data to display on map.")
        return
    map_dest_counts = get_destination_column(
        df_map, direction, focus_airport
    ).value_counts()
    if top_arcs_n is not None and top_arcs_n > 0:
        map_dest_counts = map_dest_counts.head(top_arcs_n)
    map_data = build_map_points(map_dest_counts, map_by_country)
    map_df = pd.DataFrame(map_data)
    if map_df.empty:
        st.info("No destination airports with valid coordinates in the reference data.")
        return
    f_info = get_airport(focus_airport)
    f_label = (
        f"{focus_airport} ({f_info.city})" if f_info and f_info.city else focus_airport
    )
    _arc_widths = [1.0, 2.4, 4.4, 7.0]
    _arc_colors = ["#7ecbff", "#2196f3", "#ff9800", "#e53935"]

    def _spoke_buckets(pt_df: pd.DataFrame, line_color: str | None) -> None:
        """Draw focus→destination spokes bucketed by count into 4 width+color bands."""
        if pt_df.empty:
            return
        q25, q50, q75 = (
            pt_df["count"].quantile(0.25),
            pt_df["count"].quantile(0.50),
            pt_df["count"].quantile(0.75),
        )
        bucket_lons: list[list[float | None]] = [[] for _ in _arc_widths]
        bucket_lats: list[list[float | None]] = [[] for _ in _arc_widths]
        for _, row in pt_df.iterrows():
            cnt = row["count"]
            b = 3 if cnt > q75 else (2 if cnt > q50 else (1 if cnt > q25 else 0))
            bucket_lons[b] += [focus_lon, row["lon"], None]
            bucket_lats[b] += [focus_lat, row["lat"], None]
        for b, (width, bcolor) in enumerate(zip(_arc_widths, _arc_colors)):
            if bucket_lons[b]:
                fig_map.add_trace(
                    go.Scattergeo(
                        lon=bucket_lons[b],
                        lat=bucket_lats[b],
                        mode="lines",
                        line=dict(
                            width=width,
                            color=bcolor if line_color is None else line_color,
                        ),
                        opacity=0.5,
                        hoverinfo="skip",
                        showlegend=False,
                    )
                )

    fig_map = go.Figure()
    if not airline_codes:
        _spoke_buckets(map_df, line_color=None)
        fig_map.add_trace(
            go.Scattergeo(
                lon=map_df["lon"],
                lat=map_df["lat"],
                text=map_df["label"],
                mode="markers",
                marker=dict(
                    size=map_df["count"].clip(upper=2000) ** 0.5 + 3,
                    color=map_df["count"],
                    colorscale="Viridis",
                    showscale=True,
                    colorbar=dict(title="Flights"),
                ),
                hoverinfo="text",
                showlegend=False,
            )
        )
        show_legend = False
    else:
        palette = px.colors.qualitative.Plotly
        airline_summaries: list[str] = []
        for idx, code in enumerate(airline_codes):
            color = palette[idx % len(palette)]
            a_info = get_airline(code)
            a_name = a_info.name if a_info else code
            df_a = df_map[df_map[airline_col] == code]
            a_dest_counts = get_destination_column(
                df_a, direction, focus_airport
            ).value_counts()
            if top_arcs_n is not None and top_arcs_n > 0:
                a_dest_counts = a_dest_counts.head(top_arcs_n)
            a_points = build_map_points(a_dest_counts, map_by_country)
            a_df = pd.DataFrame(a_points)
            if a_df.empty:
                continue
            airline_summaries.append(f"{a_name}: {len(df_a):,} flights")
            _spoke_buckets(a_df, line_color=None if use_traffic_colors else color)
            fig_map.add_trace(
                go.Scattergeo(
                    lon=a_df["lon"],
                    lat=a_df["lat"],
                    text=a_df["label"].apply(lambda lbl, n=a_name: f"{n} | {lbl}"),
                    mode="markers",
                    marker=dict(
                        size=a_df["count"].clip(upper=2000) ** 0.5 + 3,
                        color=color,
                    ),
                    hoverinfo="text",
                    name=a_name,
                    showlegend=True,
                )
            )
        if airline_summaries:
            st.caption(" / ".join(airline_summaries))
        elif airline_codes:
            st.info(
                "No destination airports with valid coordinates for the selected airlines."
            )
            return
        show_legend = bool(airline_codes)
    fig_map.add_trace(
        go.Scattergeo(
            lon=[focus_lon],
            lat=[focus_lat],
            text=[f_label],
            mode="markers+text",
            marker=dict(size=15, color="red", symbol="star"),
            textfont=dict(color="black"),
            textposition="top center",
            hoverinfo="text",
            showlegend=False,
        )
    )
    fig_map.update_geos(**_get_map_geo_opts(geo_scope, (focus_lat, focus_lon)))
    fig_map.update_layout(
        height=600,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=show_legend,
    )
    st.plotly_chart(fig_map, width="stretch")


def _render_network_map(
    df_map: pd.DataFrame,
    airline_col: str,
    airline_codes: list[str],
    geo_scope: str = "usa",
    top_routes_n: int = 50,
) -> None:
    """Render a global network map: airport bubbles sized by traffic + top-N route arcs.

    When airline_codes is non-empty, draw each airline's routes in a distinct color.
    """
    if df_map.empty:
        st.info("No flight data to display on map.")
        return

    palette = px.colors.qualitative.Plotly
    fig_map = go.Figure()

    def _add_airport_bubbles(
        df_sub: pd.DataFrame, color: str | None, name: str
    ) -> None:
        traffic = (
            pd.concat(
                [
                    df_sub["origin"].value_counts(),
                    df_sub["destination"].value_counts(),
                ]
            )
            .groupby(level=0)
            .sum()
            .sort_values(ascending=False)
        )
        pts: list[dict] = []
        for iata, cnt in traffic.items():
            info = get_airport(iata)
            if info and (info.latitude != 0 or info.longitude != 0):
                pts.append(
                    {
                        "iata": iata,
                        "lat": info.latitude,
                        "lon": info.longitude,
                        "count": cnt,
                        "label": f"{iata} ({info.city or '?'}): {cnt:,} flights",
                    }
                )
        if not pts:
            return
        pt_df = pd.DataFrame(pts)
        marker_kw: dict = dict(
            size=pt_df["count"].clip(upper=5000) ** 0.45 + 3,
            sizemode="diameter",
        )
        if color:
            marker_kw["color"] = color
        else:
            marker_kw.update(
                color=pt_df["count"],
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="Flights"),
            )
        fig_map.add_trace(
            go.Scattergeo(
                lon=pt_df["lon"],
                lat=pt_df["lat"],
                text=pt_df["label"],
                mode="markers",
                marker=marker_kw,
                hoverinfo="text",
                name=name,
                showlegend=bool(color),
            )
        )

    def _add_route_arcs(df_sub: pd.DataFrame, color: str, n: int) -> None:
        route_counts = (
            df_sub.groupby(["origin", "destination"])
            .size()
            .sort_values(ascending=False)
            .head(n)
        )
        if route_counts.empty:
            return
        # Bucket routes into 4 bands by quartile; each band gets a distinct width and color.
        # Colors run cool → warm to signal route popularity (low → high traffic).
        _widths = [1.0, 2.4, 4.4, 7.0]
        _colors = ["#7ecbff", "#2196f3", "#ff9800", "#e53935"]  # blue → orange → red
        q25, q50, q75 = (
            route_counts.quantile(0.25),
            route_counts.quantile(0.50),
            route_counts.quantile(0.75),
        )
        bucket_lons: list[list[float | None]] = [[] for _ in _widths]
        bucket_lats: list[list[float | None]] = [[] for _ in _widths]
        for (orig, dest), cnt in route_counts.items():
            o_info = get_airport(orig)
            d_info = get_airport(dest)
            if not o_info or not d_info:
                continue
            if o_info.latitude == 0 and o_info.longitude == 0:
                continue
            if d_info.latitude == 0 and d_info.longitude == 0:
                continue
            b = 3 if cnt > q75 else (2 if cnt > q50 else (1 if cnt > q25 else 0))
            bucket_lons[b] += [o_info.longitude, d_info.longitude, None]
            bucket_lats[b] += [o_info.latitude, d_info.latitude, None]
        for b, (width, bcolor) in enumerate(zip(_widths, _colors)):
            if bucket_lons[b]:
                fig_map.add_trace(
                    go.Scattergeo(
                        lon=bucket_lons[b],
                        lat=bucket_lats[b],
                        mode="lines",
                        line=dict(width=width, color=bcolor),
                        opacity=0.5,
                        hoverinfo="skip",
                        showlegend=False,
                    )
                )

    if not airline_codes:
        arc_color = "rgba(100,150,200,0.6)"
        _add_route_arcs(df_map, arc_color, top_routes_n)
        _add_airport_bubbles(df_map, None, "Airports")
        show_legend = False
    else:
        summaries: list[str] = []
        for idx, code in enumerate(airline_codes):
            color = palette[idx % len(palette)]
            a_info = get_airline(code)
            a_name = a_info.name if a_info else code
            df_a = df_map[df_map[airline_col] == code]
            if df_a.empty:
                continue
            summaries.append(f"{a_name}: {len(df_a):,} flights")
            _add_route_arcs(df_a, color, top_routes_n)
            _add_airport_bubbles(df_a, color, a_name)
        if summaries:
            st.caption(" / ".join(summaries))
        show_legend = True

    fig_map.update_geos(**_get_map_geo_opts(geo_scope))
    fig_map.update_layout(
        height=600,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=show_legend,
    )
    st.plotly_chart(fig_map, width="stretch")


def _airline_label(code: str) -> str:
    info = get_airline(code)
    return f"{code} - {info.name}" if info and info.name else code


def _route_label(origin: str, destination: str) -> str:
    o_info = get_airport(origin)
    d_info = get_airport(destination)
    o_label = f"{origin} ({o_info.city})" if o_info and o_info.city else origin
    d_label = (
        f"{destination} ({d_info.city})" if d_info and d_info.city else destination
    )
    return f"{o_label} → {d_label}"


RouteCityKey = tuple[str, str]


def _airport_city_key(iata: str) -> RouteCityKey:
    info = get_airport(iata)
    if info and info.city:
        return (info.city, info.country or "")
    return (iata, "")


def _city_key_label(city_key: RouteCityKey) -> str:
    city, country = city_key
    return f"{city}, {country}" if country else city


def _city_key_display(city_key: RouteCityKey, iatas: set[str] | None = None) -> str:
    label = _city_key_label(city_key)
    if not iatas:
        return label
    return f"{label} ({'/'.join(sorted(iatas))})"


def _format_insight_table(df: pd.DataFrame) -> pd.DataFrame:
    """Add readable labels and display-friendly column names for insight tables."""
    if df.empty:
        return df

    display = df.copy()
    if {"origin", "destination"}.issubset(display.columns):
        display.insert(
            0,
            "Route",
            display.apply(
                lambda r: _route_label(r["origin"], r["destination"]), axis=1
            ),
        )
    if "airline" in display.columns:
        display.insert(0, "Airline", display["airline"].apply(_airline_label))

    return display.rename(
        columns={
            "airline": "ICAO",
            "origin": "Origin",
            "destination": "Destination",
            "previous_flights": "Previous flights",
            "current_flights": "Current flights",
            "previous_flights_per_day": "Previous flights/day",
            "current_flights_per_day": "Current flights/day",
            "absolute_change_per_day": "Change/day",
            "percent_change": "Change (%)",
        }
    )


def _render_insight_grid(title: str, df: pd.DataFrame, empty_message: str) -> None:
    st.subheader(title)
    if df.empty:
        st.caption(empty_message)
        return

    display = _format_insight_table(df)
    gb = GridOptionsBuilder.from_dataframe(display)
    # Prefer flex over autoSizeStrategy=fitGridWidth: the one-shot fit can lock
    # tiny widths before the Streamlit component iframe finishes sizing.
    gb.configure_default_column(
        sortable=True,
        filter=True,
        resizable=True,
        flex=1,
        minWidth=100,
    )
    if "Airline" in display.columns:
        gb.configure_column("Airline", flex=2, minWidth=150)
    if "Route" in display.columns:
        gb.configure_column("Route", flex=3, minWidth=220)
    grid_options = gb.build()
    grid_options.pop("autoSizeStrategy", None)
    height = min(420, 80 + 35 * len(display))
    AgGrid(
        display,
        gridOptions=grid_options,
        height=height,
    )


def _default_current_period_index(period_options: list[str]) -> int:
    """Default to the period before the latest one when possible."""
    if len(period_options) >= 2:
        return len(period_options) - 2
    return 0


def _comparison_period_options(
    period_options: list[str], current_period: str
) -> tuple[list[str], int]:
    """Return comparison choices and the default index for the selected period."""
    comparison_options = [p for p in period_options if p != current_period]
    if not comparison_options:
        return [], 0

    current_idx = period_options.index(current_period)
    default_period = (
        period_options[current_idx - 1] if current_idx > 0 else comparison_options[0]
    )
    return comparison_options, comparison_options.index(default_period)


def _render_insight_chart(
    title: str,
    df: pd.DataFrame,
    *,
    value_col: str,
    value_label: str,
    color_scale: str,
    empty_message: str,
    top_n: int,
    ascending: bool = False,
) -> None:
    st.subheader(title)
    if df.empty:
        st.caption(empty_message)
        return

    sorted_df = df.sort_values(value_col, ascending=ascending).head(top_n)
    plot_df = _format_insight_table(sorted_df)
    if value_label not in plot_df.columns:
        plot_df = plot_df.rename(columns={value_col: value_label})
    if {"Airline", "Route"}.issubset(plot_df.columns):
        plot_df["Airline route"] = plot_df["Airline"] + " | " + plot_df["Route"]
        label_col = "Airline route"
    else:
        label_col = "Route" if "Route" in plot_df.columns else "Airline"
    hover_cols = [
        col
        for col in [
            "Airline",
            "Route",
            "Previous flights",
            "Current flights",
            "Change/day",
            "Change (%)",
        ]
        if col in plot_df.columns and col != value_label
    ]
    fig = px.bar(
        plot_df.sort_values(value_label, ascending=ascending),
        x=value_label,
        y=label_col,
        orientation="h",
        color=value_label,
        color_continuous_scale=color_scale,
        hover_data=hover_cols,
    )
    fig.update_layout(
        height=360, yaxis={"categoryorder": "total ascending"}, showlegend=False
    )
    if value_label in {
        "Previous flights",
        "Current flights",
        "Number of flights",
        "Flights",
    }:
        _start_flight_count_axis_at_zero(fig, "x")
    st.plotly_chart(fig, width="stretch")


def _slice_period(df: pd.DataFrame, window) -> pd.DataFrame:
    dates = pd.to_datetime(df["date"]).dt.normalize()
    return df[(dates >= window.start) & (dates <= window.end)]


def _filter_df_for_insight_routes(
    df_period: pd.DataFrame,
    routes_df: pd.DataFrame,
    *,
    airline_col: str,
    bidirectional_focus_airport: str | None,
) -> pd.DataFrame:
    if df_period.empty or routes_df.empty:
        return df_period.iloc[0:0]

    include_airline = (
        "airline" in routes_df.columns and airline_col in df_period.columns
    )
    if bidirectional_focus_airport:
        work = df_period.copy()
        touches_focus = (work["origin"] == bidirectional_focus_airport) | (
            work["destination"] == bidirectional_focus_airport
        )
        counterpart = work["destination"].where(
            work["origin"] == bidirectional_focus_airport,
            work["origin"],
        )
        work["_insight_origin"] = work["origin"].where(
            ~touches_focus, bidirectional_focus_airport
        )
        work["_insight_destination"] = work["destination"].where(
            ~touches_focus, counterpart
        )
        match = (
            routes_df[["origin", "destination"]]
            .drop_duplicates()
            .rename(
                columns={
                    "origin": "_insight_origin",
                    "destination": "_insight_destination",
                }
            )
        )
        keys = ["_insight_origin", "_insight_destination"]
    else:
        work = df_period.copy()
        match = routes_df[["origin", "destination"]].drop_duplicates()
        keys = ["origin", "destination"]

    if include_airline:
        match = routes_df[["airline", "origin", "destination"]].drop_duplicates()
        if bidirectional_focus_airport:
            match = match.rename(
                columns={
                    "airline": airline_col,
                    "origin": "_insight_origin",
                    "destination": "_insight_destination",
                }
            )
            keys = [airline_col, "_insight_origin", "_insight_destination"]
        else:
            match = match.rename(columns={"airline": airline_col})
            keys = [airline_col, "origin", "destination"]

    filtered = work.merge(match, on=keys, how="inner")
    return filtered.drop(
        columns=[
            c
            for c in ["_insight_origin", "_insight_destination"]
            if c in filtered.columns
        ]
    )


def _render_insight_route_map(
    title: str,
    df: pd.DataFrame,
    routes_df: pd.DataFrame,
    window,
    *,
    airline_col: str,
    bidirectional_focus_airport: str | None,
    global_mode: bool,
    direction: str,
    focus_airport: str | None,
    focus_lat: float,
    focus_lon: float,
    geo_scope: str,
    top_routes_n: int,
) -> None:
    st.subheader(title)
    map_period_df = _slice_period(df, window)
    insight_map_df = _filter_df_for_insight_routes(
        map_period_df,
        routes_df,
        airline_col=airline_col,
        bidirectional_focus_airport=bidirectional_focus_airport,
    )
    if insight_map_df.empty:
        st.caption("No route rows are available to map for this insight category.")
        return
    if global_mode:
        _render_network_map(insight_map_df, airline_col, [], geo_scope, top_routes_n)
        return
    if focus_airport is None:
        st.caption("A focus airport is required to render this route map.")
        return
    _render_flight_map(
        insight_map_df,
        direction,
        focus_airport,
        focus_lat,
        focus_lon,
        False,
        [],
        airline_col,
        geo_scope,
        top_arcs_n=top_routes_n,
    )


def main() -> None:
    st.set_page_config(
        page_title="Flight Dashboard",
        page_icon="✈️",
        layout="wide",
    )

    # ── Sidebar: dataset ──
    with st.sidebar:
        st.header("Dataset")
        dataset_key = st.radio(
            "Dataset",
            options=list(DATASETS.keys()),
            index=0,
            label_visibility="collapsed",
        )

    ds = DATASETS[dataset_key]
    geo_scope = ds["scope"]
    is_us = dataset_key == "US Domestic"
    show_country = not is_us

    df_all = load_flights(dataset_key)

    # ── Sidebar: mode (US) + focus airport ──
    with st.sidebar:
        if is_us:
            st.markdown("---")
            st.header("Mode")
            mode_sel = st.radio(
                "Mode",
                options=["Global network", "Focus airport"],
                index=0,
                label_visibility="collapsed",
            )
            global_mode = mode_sel == "Global network"
        else:
            global_mode = False

        if ds["default_airport"]:
            focus_airport: str | None = ds["default_airport"]
        elif global_mode:
            focus_airport = None
        else:
            airport_traffic = (
                pd.concat(
                    [
                        df_all["origin"].value_counts(),
                        df_all["destination"].value_counts(),
                    ]
                )
                .groupby(level=0)
                .sum()
                .sort_values(ascending=False)
            )
            airport_options: list[str] = []
            airport_display_to_code: dict[str, str] = {}
            for code in airport_traffic.index:
                info = get_airport(code)
                label = f"{code} - {info.city}" if info and info.city else code
                airport_options.append(label)
                airport_display_to_code[label] = code

            st.markdown("---")
            st.header("Focus airport")
            sel_airport_display = st.selectbox(
                "Airport",
                options=airport_options,
                index=0,
                label_visibility="collapsed",
            )
            focus_airport = airport_display_to_code.get(
                sel_airport_display, airport_traffic.index[0]
            )

    if focus_airport:
        focus_info = get_airport(focus_airport)
        focus_lat = focus_info.latitude if focus_info else 0.0
        focus_lon = focus_info.longitude if focus_info else 0.0
        focus_label = (
            f"{focus_airport} ({focus_info.city})"
            if focus_info and focus_info.city
            else focus_airport
        )
    else:
        focus_lat = 0.0
        focus_lon = 0.0
        focus_label = "US Domestic"

    if global_mode:
        st.title("✈️ US Domestic Flight Dashboard")
        st.caption("Analyzing all US domestic flights")
    else:
        st.title(f"✈️ {focus_label} Flight Dashboard")
        st.caption(f"Analyze flight data to/from {focus_label}")

    min_date = df_all["date"].min().date()
    max_date = df_all["date"].max().date()

    # ── Sidebar: section & filters ──
    with st.sidebar:
        st.markdown("---")
        st.header("Section")
        section_options = [
            "Overview",
            "Insights",
            "Airline deep dive",
            "Route deep dive",
        ]
        if is_us:
            section_options.append("Delay analysis")
        section = st.radio(
            "View",
            options=section_options,
            index=0,
            label_visibility="collapsed",
            key="main_section",
        )
        st.markdown("---")
        st.header("Filters")
        if global_mode:
            direction = "Both"
        else:
            direction = st.radio(
                "Direction",
                options=["Departures", "Arrivals", "Both"],
                index=2,
                help=(
                    f"Departures = from {focus_airport}, "
                    f"Arrivals = to {focus_airport}, "
                    f"Both = all flights involving {focus_airport}"
                ),
            )
        start_date = st.date_input(
            "Start date",
            value=min_date,
            min_value=min_date,
            max_value=max_date,
        )
        end_date = st.date_input(
            "End date",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
        )
        top_n = st.slider("Top N for rankings", min_value=5, max_value=50, value=10)

        has_cargo = "cargo" in df_all.columns
        if has_cargo and not is_us:
            cargo_filter = st.radio(
                "Flight type",
                options=["All", "Passenger only", "Cargo only"],
                index=1,
                help="Filter by passenger vs cargo flights",
            )
        elif is_us:
            cargo_filter = "Passenger only"
        else:
            cargo_filter = None

        has_operating = "operating_airline" in df_all.columns
        if has_operating:
            operating_only = st.checkbox(
                "Operating carrier only",
                value=True,
                help="Exclude code-share duplicates; show one row per physical flight",
            )
        else:
            operating_only = False

    if start_date > end_date:
        st.error("Start date must be before or equal to end date.")
        return

    df = apply_filters(
        df_all,
        direction,
        focus_airport,
        pd.Timestamp(start_date),
        pd.Timestamp(end_date),
        cargo_filter=cargo_filter if has_cargo else None,
        operating_only=operating_only if has_operating else False,
    )
    total_flights = len(df)

    st.metric("Total flights (filtered)", f"{total_flights:,}")

    airline_col = (
        "operating_airline" if (operating_only and has_operating) else "airline"
    )

    # ══════════════════════════════════════════════════════════════════════
    #  OVERVIEW
    # ══════════════════════════════════════════════════════════════════════
    if section == "Overview":
        chart_h = 320
        airline_counts = df[airline_col].value_counts()
        top_airlines = airline_counts.head(top_n)
        airline_rows = []
        for icao, count in top_airlines.items():
            info = get_airline(icao)
            share = 100 * count / total_flights if total_flights > 0 else 0
            airline_rows.append(
                {
                    "Airline": info.name if info else icao,
                    "Flights": count,
                    "Share (%)": round(share, 1),
                }
            )
        airline_df = pd.DataFrame(
            airline_rows, columns=["Airline", "Flights", "Share (%)"]
        )
        fig_airlines = px.bar(
            airline_df,
            x="Flights",
            y="Airline",
            orientation="h",
            color="Flights",
            color_continuous_scale="Blues",
            text=airline_df["Share (%)"].apply(lambda x: f"{x}%"),
        )
        fig_airlines.update_traces(textposition="outside")
        fig_airlines.update_layout(
            height=chart_h, yaxis={"categoryorder": "total ascending"}, showlegend=False
        )
        _start_flight_count_axis_at_zero(fig_airlines, "x")

        if global_mode:
            # ── Global mode: top routes + top airports ──
            route_counts_all = (
                df.groupby(["origin", "destination"])
                .size()
                .sort_values(ascending=False)
            )
            route_rows: list[dict] = []
            for (orig, dest), cnt in route_counts_all.head(top_n).items():
                o_info = get_airport(orig)
                d_info = get_airport(dest)
                o_label = f"{orig} ({o_info.city})" if o_info and o_info.city else orig
                d_label = f"{dest} ({d_info.city})" if d_info and d_info.city else dest
                share = 100 * cnt / total_flights if total_flights > 0 else 0
                route_rows.append(
                    {
                        "Route": f"{o_label} → {d_label}",
                        "Flights": cnt,
                        "Share (%)": round(share, 1),
                    }
                )
            route_overview_df = pd.DataFrame(
                route_rows, columns=["Route", "Flights", "Share (%)"]
            )

            apt_traffic = (
                pd.concat(
                    [
                        df["origin"].value_counts(),
                        df["destination"].value_counts(),
                    ]
                )
                .groupby(level=0)
                .sum()
                .sort_values(ascending=False)
            )
            apt_rows: list[dict] = []
            for iata, cnt in apt_traffic.head(top_n).items():
                info = get_airport(iata)
                share = 100 * cnt / total_flights if total_flights > 0 else 0
                label = f"{iata} - {info.name}" if info and info.name else iata
                apt_rows.append(
                    {"Label": label, "Flights": cnt, "Share (%)": round(share, 1)}
                )
            apt_overview_df = pd.DataFrame(
                apt_rows, columns=["Label", "Flights", "Share (%)"]
            )

            city_counts_g: dict[str, int] = {}
            for iata, cnt in apt_traffic.items():
                info = get_airport(iata)
                city = info.city if info and info.city else iata
                city_counts_g[city] = city_counts_g.get(city, 0) + cnt
            city_sorted_g = sorted(city_counts_g.items(), key=lambda x: -x[1])[:top_n]
            city_df_g = pd.DataFrame(
                [{"City": c, "Flights": n} for c, n in city_sorted_g],
                columns=["City", "Flights"],
            )
            city_df_g["Share (%)"] = (
                (100 * city_df_g["Flights"] / total_flights).round(1)
                if total_flights
                else 0.0
            )

            fig_routes_ov = px.bar(
                route_overview_df,
                x="Flights",
                y="Route",
                orientation="h",
                color="Flights",
                color_continuous_scale="Greens",
                text=route_overview_df["Share (%)"].apply(lambda x: f"{x}%"),
            )
            fig_routes_ov.update_traces(textposition="outside")
            fig_routes_ov.update_layout(
                height=chart_h + 80,
                yaxis={"categoryorder": "total ascending"},
                showlegend=False,
            )
            _start_flight_count_axis_at_zero(fig_routes_ov, "x")

            fig_apt_ov = px.bar(
                apt_overview_df,
                x="Flights",
                y="Label",
                orientation="h",
                color="Flights",
                color_continuous_scale="Oranges",
                text=apt_overview_df["Share (%)"].apply(lambda x: f"{x}%"),
            )
            fig_apt_ov.update_traces(textposition="outside")
            fig_apt_ov.update_layout(
                height=chart_h,
                yaxis={"categoryorder": "total ascending"},
                showlegend=False,
            )
            _start_flight_count_axis_at_zero(fig_apt_ov, "x")

            fig_city_g = px.bar(
                city_df_g,
                x="Flights",
                y="City",
                orientation="h",
                color="Flights",
                color_continuous_scale="Purples",
                text=city_df_g["Share (%)"].apply(lambda x: f"{x}%"),
            )
            fig_city_g.update_traces(textposition="outside")
            fig_city_g.update_layout(
                height=chart_h,
                yaxis={"categoryorder": "total ascending"},
                showlegend=False,
            )
            _start_flight_count_axis_at_zero(fig_city_g, "x")

            r1c1, r1c2 = st.columns(2)
            with r1c1:
                st.subheader("Top airlines by flight count")
                st.plotly_chart(fig_airlines, width="stretch")
            with r1c2:
                st.subheader("Top airports by total traffic")
                st.plotly_chart(fig_apt_ov, width="stretch")

            r2c1, r2c2 = st.columns(2)
            with r2c1:
                st.subheader("Top routes (O-D pairs)")
                st.plotly_chart(fig_routes_ov, width="stretch")
            with r2c2:
                st.subheader("Top cities by total traffic")
                st.plotly_chart(fig_city_g, width="stretch")

            # ── Flights per day ──
            st.header("Flights per day")
            flights_per_day = (
                df.groupby(df["date"].dt.date).size().reset_index(name="Flights")
            )
            flights_per_day.columns = ["Date", "Flights"]
            flights_per_day = _complete_daily_series(
                flights_per_day,
                date_col="Date",
                value_cols=["Flights"],
                start_date=start_date,
                end_date=end_date,
            )
            if not flights_per_day.empty:
                fig_per_day = px.line(
                    flights_per_day,
                    x="Date",
                    y="Flights",
                    labels={"Date": "Date", "Flights": "Number of flights"},
                )
                fig_per_day.update_layout(height=350)
                _start_flight_count_axis_at_zero(fig_per_day, "y")
                st.plotly_chart(fig_per_day, width="stretch")
            else:
                st.caption("No date data.")

            # ── Network map ──
            st.header("US domestic network map")
            map_airline_col = (
                "operating_airline" if (operating_only and has_operating) else "airline"
            )
            map_airlines_g = sorted(df[map_airline_col].dropna().unique().tolist())
            map_airline_display_g: list[str] = []
            map_display_to_code_g: dict[str, str] = {}
            for code in map_airlines_g:
                display = (
                    f"{code} - {info.name}"
                    if (info := get_airline(code)) and info.name
                    else code
                )
                map_airline_display_g.append(display)
                map_display_to_code_g[display] = code

            sel_map_airlines_g = st.multiselect(
                "Filter by airlines",
                options=map_airline_display_g,
                default=[],
                help="Leave empty to show all. Select airlines to compare with distinct colors.",
                key="overview_g_map_airlines",
            )
            sel_map_codes_g = [
                map_display_to_code_g[d]
                for d in sel_map_airlines_g
                if d in map_display_to_code_g
            ]
            _render_network_map(df, map_airline_col, sel_map_codes_g, geo_scope, top_n)

        else:
            # ── Focus mode: top destinations ──
            dest_codes = get_destination_column(df, direction, focus_airport)
            dest_counts = dest_codes.value_counts()

            airport_rows = []
            for iata, count in dest_counts.head(top_n).items():
                info = get_airport(iata)
                share = 100 * count / total_flights if total_flights > 0 else 0
                label = f"{iata} - {info.name}" if info and info.name else iata
                airport_rows.append(
                    {"Label": label, "Flights": count, "Share (%)": round(share, 1)}
                )
            airport_df = pd.DataFrame(
                airport_rows, columns=["Label", "Flights", "Share (%)"]
            )

            city_counts: dict[str, int] = {}
            for iata, count in dest_counts.items():
                info = get_airport(iata)
                city = info.city if info and info.city else iata
                city_counts[city] = city_counts.get(city, 0) + count
            city_sorted = sorted(city_counts.items(), key=lambda x: -x[1])[:top_n]
            city_df = pd.DataFrame(
                [{"City": c, "Flights": n} for c, n in city_sorted],
                columns=["City", "Flights"],
            )
            city_df["Share (%)"] = (
                (100 * city_df["Flights"] / total_flights).round(1)
                if total_flights
                else 0.0
            )

            if show_country:
                country_counts: dict[str, int] = {}
                for iata, count in dest_counts.items():
                    info = get_airport(iata)
                    country = info.country if info and info.country else iata
                    country_counts[country] = country_counts.get(country, 0) + count
                country_sorted = sorted(country_counts.items(), key=lambda x: -x[1])[
                    :top_n
                ]
                country_df = pd.DataFrame(
                    [{"Country": c, "Flights": n} for c, n in country_sorted],
                    columns=["Country", "Flights"],
                )
                country_df["Share (%)"] = (
                    (100 * country_df["Flights"] / total_flights).round(1)
                    if total_flights
                    else 0.0
                )

            fig_apt = px.bar(
                airport_df,
                x="Flights",
                y="Label",
                orientation="h",
                color="Flights",
                color_continuous_scale="Greens",
                text=airport_df["Share (%)"].apply(lambda x: f"{x}%"),
            )
            fig_apt.update_traces(textposition="outside")
            fig_apt.update_layout(
                height=chart_h,
                yaxis={"categoryorder": "total ascending"},
                showlegend=False,
            )
            _start_flight_count_axis_at_zero(fig_apt, "x")

            fig_city = px.bar(
                city_df,
                x="Flights",
                y="City",
                orientation="h",
                color="Flights",
                color_continuous_scale="Oranges",
                text=city_df["Share (%)"].apply(lambda x: f"{x}%"),
            )
            fig_city.update_traces(textposition="outside")
            fig_city.update_layout(
                height=chart_h,
                yaxis={"categoryorder": "total ascending"},
                showlegend=False,
            )
            _start_flight_count_axis_at_zero(fig_city, "x")

            if show_country:
                fig_country = px.bar(
                    country_df,
                    x="Flights",
                    y="Country",
                    orientation="h",
                    color="Flights",
                    color_continuous_scale="Purples",
                    text=country_df["Share (%)"].apply(lambda x: f"{x}%"),
                )
                fig_country.update_traces(textposition="outside")
                fig_country.update_layout(
                    height=chart_h,
                    yaxis={"categoryorder": "total ascending"},
                    showlegend=False,
                )
                _start_flight_count_axis_at_zero(fig_country, "x")

            r1c1, r1c2 = st.columns(2)
            with r1c1:
                st.subheader("Top airlines by flight count")
                st.plotly_chart(fig_airlines, width="stretch")
            with r1c2:
                st.subheader("Top destinations by airport")
                st.plotly_chart(fig_apt, width="stretch")

            if show_country:
                r2c1, r2c2 = st.columns(2)
                with r2c1:
                    st.subheader("Top destinations by city")
                    st.plotly_chart(fig_city, width="stretch")
                with r2c2:
                    st.subheader("Top destinations by country")
                    st.plotly_chart(fig_country, width="stretch")
            else:
                st.subheader("Top destinations by city")
                st.plotly_chart(fig_city, width="stretch")

            # ── Flights per day ──
            st.header("Flights per day")
            flights_per_day = (
                df.groupby(df["date"].dt.date).size().reset_index(name="Flights")
            )
            flights_per_day.columns = ["Date", "Flights"]
            flights_per_day = _complete_daily_series(
                flights_per_day,
                date_col="Date",
                value_cols=["Flights"],
                start_date=start_date,
                end_date=end_date,
            )
            if not flights_per_day.empty:
                fig_per_day = px.line(
                    flights_per_day,
                    x="Date",
                    y="Flights",
                    labels={"Date": "Date", "Flights": "Number of flights"},
                )
                fig_per_day.update_layout(height=350)
                _start_flight_count_axis_at_zero(fig_per_day, "y")
                st.plotly_chart(fig_per_day, width="stretch")
            else:
                st.caption("No date data.")

            # ── Interactive Map ──
            st.header("Interactive map: flight flow by destination")

            map_airline_col = (
                "operating_airline" if (operating_only and has_operating) else "airline"
            )
            map_airlines = sorted(df[map_airline_col].dropna().unique().tolist())
            map_airline_display: list[str] = []
            map_display_to_code: dict[str, str] = {}
            for code in map_airlines:
                display = (
                    f"{code} - {info.name}"
                    if (info := get_airline(code)) and info.name
                    else code
                )
                map_airline_display.append(display)
                map_display_to_code[display] = code

            _dest_codes_for_countries = get_destination_column(
                df, direction, focus_airport
            )
            _country_set: set[str] = set()
            _iata_to_country: dict[str, str] = {}
            for _iata in _dest_codes_for_countries.unique():
                _info = get_airport(_iata)
                if _info and _info.country:
                    _country_set.add(_info.country)
                    _iata_to_country[_iata] = _info.country
            map_country_options = sorted(_country_set)

            if show_country:
                col_map_by, col_map_airline, col_map_country = st.columns(3)
            else:
                col_map_by, col_map_airline = st.columns(2)
                col_map_country = None

            with col_map_by:
                map_point_opts = ["City (airport)"]
                if show_country:
                    map_point_opts.append("Country")
                map_point_by = st.radio(
                    "Map points by",
                    options=map_point_opts,
                    index=0,
                    horizontal=True,
                    help="Show each destination as a precise city/airport, or aggregate by country.",
                )
            with col_map_airline:
                sel_map_airlines = st.multiselect(
                    "Filter by airlines",
                    options=map_airline_display,
                    default=[],
                    help="Leave empty to show all. Select airlines to compare on map with distinct colors.",
                )
            if col_map_country is not None:
                with col_map_country:
                    sel_map_countries = st.multiselect(
                        "Filter by country",
                        options=map_country_options,
                        default=[],
                        help="Leave empty to show all. Select countries to show only routes to those countries.",
                    )
            else:
                sel_map_countries = []

            map_by_country = map_point_by == "Country"
            sel_map_codes = [
                map_display_to_code[d]
                for d in sel_map_airlines
                if d in map_display_to_code
            ]

            if sel_map_countries:
                _allowed_iatas = {
                    iata
                    for iata, c in _iata_to_country.items()
                    if c in sel_map_countries
                }
                if direction == "Departures":
                    _country_mask = df["destination"].isin(_allowed_iatas)
                elif direction == "Arrivals":
                    _country_mask = df["origin"].isin(_allowed_iatas)
                else:
                    _country_mask = df["destination"].isin(_allowed_iatas) | df[
                        "origin"
                    ].isin(_allowed_iatas)
                df_map = df[_country_mask]
            else:
                df_map = df

            _render_flight_map(
                df_map,
                direction,
                focus_airport,
                focus_lat,
                focus_lon,
                map_by_country,
                sel_map_codes,
                map_airline_col,
                geo_scope,
                top_arcs_n=top_n,
            )

    # ══════════════════════════════════════════════════════════════════════
    #  INSIGHTS
    # ══════════════════════════════════════════════════════════════════════
    elif section == "Insights":
        st.header("Periodic insights")
        st.caption("Compare any two weeks or months using the current filters.")

        if df.empty:
            st.info("No flight data available for the selected filters.")
            return

        ctl_kind, ctl_current, ctl_comparison = st.columns(3)
        with ctl_kind:
            period_label = st.selectbox(
                "Period type",
                options=["Weekly", "Monthly"],
                index=1,
                key="insights_period_kind",
            )
            period_kind = "weekly" if period_label == "Weekly" else "monthly"
            period_options = available_period_labels(df, period_kind)
            if len(period_options) < 2:
                st.info("At least two periods are required for insights.")
                return
        with ctl_current:
            current_period = st.selectbox(
                "Current period",
                options=period_options,
                index=_default_current_period_index(period_options),
                key="insights_current_period",
                help="Defaults to the period before the latest available period because the latest period may be incomplete.",
            )
        comparison_options, comparison_default_idx = _comparison_period_options(
            period_options, current_period
        )
        with ctl_comparison:
            comparison_period = st.selectbox(
                "Compare with",
                options=comparison_options,
                index=comparison_default_idx,
                key="insights_comparison_period",
                help="Defaults to the same-frequency period immediately before the selected current period.",
            )

        insights_airline_col = (
            airline_col
            if airline_col in df.columns
            else (
                DEFAULT_COMPANY_AIRLINE_COL
                if DEFAULT_COMPANY_AIRLINE_COL in df.columns
                else MARKETING_AIRLINE_COL
            )
        )
        bidirectional_focus_airport = (
            focus_airport if direction == "Both" and focus_airport else None
        )

        ctl_baseline, ctl_abs, ctl_pct = st.columns(3)
        with ctl_baseline:
            min_previous_flights = st.number_input(
                "Minimum comparison flights",
                min_value=1,
                max_value=10_000,
                value=DEFAULT_MIN_PREVIOUS_FLIGHTS,
                step=1,
                help="Ignore frequency changes on very small baseline routes.",
                key="insights_min_previous_flights",
            )
        with ctl_abs:
            min_absolute_change = st.number_input(
                "Minimum change per day",
                min_value=0.1,
                max_value=1000.0,
                value=DEFAULT_MIN_ABSOLUTE_CHANGE_PER_DAY,
                step=0.1,
                help="Required normalized flights-per-day change.",
                key="insights_min_absolute_change",
            )
        with ctl_pct:
            min_percent_change = st.number_input(
                "Minimum percent change",
                min_value=1.0,
                max_value=100.0,
                value=DEFAULT_MIN_PERCENT_CHANGE,
                step=1.0,
                help="Required relative change from the comparison period.",
                key="insights_min_percent_change",
            )

        try:
            insights = compare_periods(
                df,
                period_kind=period_kind,
                current_period=current_period,
                comparison_period=comparison_period,
                airline_col=insights_airline_col,
                bidirectional_focus_airport=bidirectional_focus_airport,
                min_previous_flights=int(min_previous_flights),
                min_absolute_change_per_day=float(min_absolute_change),
                min_percent_change=float(min_percent_change),
            )
        except ValueError as exc:
            st.error(str(exc))
            return

        prev_label = f"{insights.previous.label} ({insights.previous.observed_days} observed days)"
        curr_label = (
            f"{insights.current.label} ({insights.current.observed_days} observed days)"
        )
        st.caption(f"Comparison: {prev_label} / Current: {curr_label}")

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        with m1:
            st.metric(
                "Current flights",
                f"{insights.current_total_flights:,}",
                delta=insights.current_total_flights - insights.previous_total_flights,
            )
        with m2:
            st.metric("New companies", f"{len(insights.new_companies):,}")
        with m3:
            st.metric(
                "Disappeared companies", f"{len(insights.disappeared_companies):,}"
            )
        with m4:
            st.metric("New routes", f"{len(insights.new_routes):,}")
        with m5:
            st.metric("Disappeared routes", f"{len(insights.disappeared_routes):,}")
        with m6:
            st.metric("Large drops", f"{len(insights.frequency_drops):,}")

        insight_tabs = st.tabs(
            ["Routes", "Companies", "Company-routes", "Frequency changes"]
        )

        with insight_tabs[1]:
            chart_new_companies, chart_disappeared_companies = st.columns(2)
            with chart_new_companies:
                _render_insight_chart(
                    "New companies by current flights",
                    insights.new_companies,
                    value_col="current_flights",
                    value_label="Current flights",
                    color_scale="Blues",
                    empty_message="No companies appeared for the first time in this period.",
                    top_n=top_n,
                )
            with chart_disappeared_companies:
                _render_insight_chart(
                    "Disappeared companies by comparison flights",
                    insights.disappeared_companies,
                    value_col="previous_flights",
                    value_label="Previous flights",
                    color_scale="Oranges",
                    empty_message="No companies disappeared in this period.",
                    top_n=top_n,
                )
            st.caption("Company-only insights do not have route maps.")
            table_new_companies, table_disappeared_companies = st.columns(2)
            with table_new_companies:
                _render_insight_grid(
                    "New companies",
                    insights.new_companies,
                    "No companies appeared for the first time in this period.",
                )
            with table_disappeared_companies:
                _render_insight_grid(
                    "Disappeared companies",
                    insights.disappeared_companies,
                    "No companies disappeared in this period.",
                )

        with insight_tabs[0]:
            chart_new_routes, chart_disappeared_routes = st.columns(2)
            with chart_new_routes:
                _render_insight_chart(
                    "New routes by current flights",
                    insights.new_routes,
                    value_col="current_flights",
                    value_label="Current flights",
                    color_scale="Greens",
                    empty_message="No routes appeared for the first time in this period.",
                    top_n=top_n,
                )
            with chart_disappeared_routes:
                _render_insight_chart(
                    "Disappeared routes by comparison flights",
                    insights.disappeared_routes,
                    value_col="previous_flights",
                    value_label="Previous flights",
                    color_scale="Oranges",
                    empty_message="No routes disappeared in this period.",
                    top_n=top_n,
                )
            map_new_routes, map_disappeared_routes = st.columns(2)
            with map_new_routes:
                _render_insight_route_map(
                    "New routes",
                    df,
                    insights.new_routes,
                    insights.current,
                    airline_col=insights_airline_col,
                    bidirectional_focus_airport=bidirectional_focus_airport,
                    global_mode=global_mode,
                    direction=direction,
                    focus_airport=focus_airport,
                    focus_lat=focus_lat,
                    focus_lon=focus_lon,
                    geo_scope=geo_scope,
                    top_routes_n=top_n,
                )
            with map_disappeared_routes:
                _render_insight_route_map(
                    "Disappeared routes",
                    df,
                    insights.disappeared_routes,
                    insights.previous,
                    airline_col=insights_airline_col,
                    bidirectional_focus_airport=bidirectional_focus_airport,
                    global_mode=global_mode,
                    direction=direction,
                    focus_airport=focus_airport,
                    focus_lat=focus_lat,
                    focus_lon=focus_lon,
                    geo_scope=geo_scope,
                    top_routes_n=top_n,
                )
            table_new_routes, table_disappeared_routes = st.columns(2)
            with table_new_routes:
                _render_insight_grid(
                    "New routes",
                    insights.new_routes,
                    "No routes appeared for the first time in this period.",
                )
            with table_disappeared_routes:
                _render_insight_grid(
                    "Disappeared routes",
                    insights.disappeared_routes,
                    "No routes disappeared in this period.",
                )

        with insight_tabs[2]:
            chart_new_company_routes, chart_disappeared_company_routes = st.columns(2)
            with chart_new_company_routes:
                _render_insight_chart(
                    "New company-routes by current flights",
                    insights.new_company_routes,
                    value_col="current_flights",
                    value_label="Current flights",
                    color_scale="Greens",
                    empty_message="No company-specific routes appeared for the first time.",
                    top_n=top_n,
                )
            with chart_disappeared_company_routes:
                _render_insight_chart(
                    "Disappeared company-routes by comparison flights",
                    insights.disappeared_company_routes,
                    value_col="previous_flights",
                    value_label="Previous flights",
                    color_scale="Oranges",
                    empty_message="No company-specific routes disappeared.",
                    top_n=top_n,
                )
            map_new_company_routes, map_disappeared_company_routes = st.columns(2)
            with map_new_company_routes:
                _render_insight_route_map(
                    "New routes by company",
                    df,
                    insights.new_company_routes,
                    insights.current,
                    airline_col=insights_airline_col,
                    bidirectional_focus_airport=bidirectional_focus_airport,
                    global_mode=global_mode,
                    direction=direction,
                    focus_airport=focus_airport,
                    focus_lat=focus_lat,
                    focus_lon=focus_lon,
                    geo_scope=geo_scope,
                    top_routes_n=top_n,
                )
            with map_disappeared_company_routes:
                _render_insight_route_map(
                    "Disappeared routes by company",
                    df,
                    insights.disappeared_company_routes,
                    insights.previous,
                    airline_col=insights_airline_col,
                    bidirectional_focus_airport=bidirectional_focus_airport,
                    global_mode=global_mode,
                    direction=direction,
                    focus_airport=focus_airport,
                    focus_lat=focus_lat,
                    focus_lon=focus_lon,
                    geo_scope=geo_scope,
                    top_routes_n=top_n,
                )
            table_new_company_routes, table_disappeared_company_routes = st.columns(2)
            with table_new_company_routes:
                _render_insight_grid(
                    "New routes by company",
                    insights.new_company_routes,
                    "No company-specific routes appeared for the first time.",
                )
            with table_disappeared_company_routes:
                _render_insight_grid(
                    "Disappeared routes by company",
                    insights.disappeared_company_routes,
                    "No company-specific routes disappeared in this period.",
                )

        with insight_tabs[3]:
            frequency_metric = st.radio(
                "Frequency change metric",
                options=["Change/day", "Change (%)"],
                index=0,
                horizontal=True,
                help="Rank frequency changes by normalized flights per day or relative percent change.",
                key="insights_frequency_metric",
            )
            frequency_value_col = (
                "percent_change"
                if frequency_metric == "Change (%)"
                else "absolute_change_per_day"
            )
            chart_frequency_increases_left, chart_frequency_drops_right = st.columns(2)
            with chart_frequency_increases_left:
                _render_insight_chart(
                    "Largest frequency increases",
                    insights.frequency_increases,
                    value_col=frequency_value_col,
                    value_label=frequency_metric,
                    color_scale="Greens",
                    empty_message="No routes crossed the increase thresholds.",
                    top_n=top_n,
                )
            with chart_frequency_drops_right:
                _render_insight_chart(
                    "Largest frequency drops",
                    insights.frequency_drops,
                    value_col=frequency_value_col,
                    value_label=frequency_metric,
                    color_scale="Reds_r",
                    empty_message="No routes crossed the drop thresholds.",
                    top_n=top_n,
                    ascending=True,
                )
            map_frequency_increases_left, map_frequency_drops_right = st.columns(2)
            with map_frequency_increases_left:
                _render_insight_route_map(
                    "Frequency increases",
                    df,
                    insights.frequency_increases,
                    insights.current,
                    airline_col=insights_airline_col,
                    bidirectional_focus_airport=bidirectional_focus_airport,
                    global_mode=global_mode,
                    direction=direction,
                    focus_airport=focus_airport,
                    focus_lat=focus_lat,
                    focus_lon=focus_lon,
                    geo_scope=geo_scope,
                    top_routes_n=top_n,
                )
            with map_frequency_drops_right:
                _render_insight_route_map(
                    "Frequency drops",
                    df,
                    insights.frequency_drops,
                    insights.current,
                    airline_col=insights_airline_col,
                    bidirectional_focus_airport=bidirectional_focus_airport,
                    global_mode=global_mode,
                    direction=direction,
                    focus_airport=focus_airport,
                    focus_lat=focus_lat,
                    focus_lon=focus_lon,
                    geo_scope=geo_scope,
                    top_routes_n=top_n,
                )
            table_frequency_increases_left, table_frequency_drops_right = st.columns(2)
            with table_frequency_increases_left:
                _render_insight_grid(
                    "Frequency increases",
                    insights.frequency_increases,
                    "No routes crossed the configured increase thresholds.",
                )
            with table_frequency_drops_right:
                _render_insight_grid(
                    "Frequency drops",
                    insights.frequency_drops,
                    "No routes crossed the configured drop thresholds.",
                )

    # ══════════════════════════════════════════════════════════════════════
    #  AIRLINE DEEP DIVE
    # ══════════════════════════════════════════════════════════════════════
    elif section == "Airline deep dive":
        st.header("Airline deep dive")
        dive_airlines = sorted(df[airline_col].dropna().unique().tolist())
        dive_airline_options: list[str] = []
        dive_display_to_code: dict[str, str] = {}
        for code in dive_airlines:
            display = (
                f"{code} - {info.name}"
                if (info := get_airline(code)) and info.name
                else code
            )
            dive_airline_options.append(display)
            dive_display_to_code[display] = code

        if not dive_airline_options:
            st.info("No airlines in the filtered data.")
        else:
            col_search_a, col_select_a = st.columns(2)
            with col_search_a:
                airline_search = st.text_input(
                    "Search airlines by code or name",
                    placeholder="e.g. CPA, Cathay, United",
                    help="Filter the airline list by typing ICAO code or airline name.",
                    key="airline_dive_search",
                )
            airline_search_lower = airline_search.strip().lower()
            if airline_search_lower:
                filtered_airlines = [
                    a for a in dive_airline_options if airline_search_lower in a.lower()
                ]
            else:
                filtered_airlines = dive_airline_options

            if not filtered_airlines:
                st.info("No airlines match your search.")
            else:
                default_dive_idx = 0
                if not is_us:
                    for i, opt in enumerate(filtered_airlines):
                        if (
                            opt.startswith("CPA -")
                            or dive_display_to_code.get(opt) == "CPA"
                        ):
                            default_dive_idx = i
                            break

                with col_select_a:
                    sel_dive_airline = st.selectbox(
                        "Select airline",
                        options=filtered_airlines,
                        index=min(default_dive_idx, len(filtered_airlines) - 1),
                        help="Explore statistics for a single airline.",
                        key="airline_dive_select",
                    )
                dive_icao = (
                    dive_display_to_code.get(sel_dive_airline, "")
                    if sel_dive_airline
                    else ""
                )
                df_airline = (
                    df[df[airline_col] == dive_icao] if dive_icao else pd.DataFrame()
                )

                if df_airline.empty:
                    st.info("No flights for this airline in the selected filters.")
                else:
                    dive_name = (
                        get_airline(dive_icao).name
                        if get_airline(dive_icao)
                        else dive_icao
                    )
                    st.subheader(f"{dive_name}")

                    n_airline = len(df_airline)
                    pct = 100 * n_airline / total_flights if total_flights > 0 else 0
                    m1, m2 = st.columns(2)
                    with m1:
                        st.metric("Total flights", f"{n_airline:,}")
                    with m2:
                        st.metric("Share of traffic", f"{pct:.1f}%")

                    dest_codes_airline = get_destination_column(
                        df_airline, direction, focus_airport
                    )
                    dest_counts_airline = dest_codes_airline.value_counts()
                    if global_mode:
                        route_dest_airline = df_airline["destination"]
                    elif direction == "Departures":
                        route_dest_airline = df_airline["destination"]
                    elif direction == "Arrivals":
                        route_dest_airline = df_airline["origin"]
                    else:
                        route_dest_airline = pd.Series(
                            np.where(
                                df_airline["origin"] == focus_airport,
                                df_airline["destination"],
                                df_airline["origin"],
                            ),
                            index=df_airline.index,
                        )

                    _dive_tab_names = [
                        "Top routes",
                        "Flights over time",
                        "Flights by hour",
                        "Flights by weekday",
                    ]
                    if not is_us:
                        _dive_tab_names.append("Cargo vs passenger")
                    _dive_tab_names.append("Interactive map")
                    _dive_tabs = st.tabs(_dive_tab_names)
                    if is_us:
                        tab_routes, tab_time, tab_hour, tab_weekday, tab_map = (
                            _dive_tabs
                        )
                        tab_cargo = None
                    else:
                        (
                            tab_routes,
                            tab_time,
                            tab_hour,
                            tab_weekday,
                            tab_cargo,
                            tab_map,
                        ) = _dive_tabs

                    with tab_routes:
                        if global_mode:
                            # Show top O-D pairs for this airline
                            od_counts_airline = (
                                df_airline.groupby(["origin", "destination"])
                                .size()
                                .sort_values(ascending=False)
                            )
                            od_total_counts = df.groupby(
                                ["origin", "destination"]
                            ).size()
                            od_n = min(top_n, len(od_counts_airline))
                            od_rows: list[dict] = []
                            for (orig, dest), cnt in od_counts_airline.head(
                                od_n
                            ).items():
                                o_info = get_airport(orig)
                                d_info = get_airport(dest)
                                o_lbl = (
                                    f"{orig} ({o_info.city})"
                                    if o_info and o_info.city
                                    else orig
                                )
                                d_lbl = (
                                    f"{dest} ({d_info.city})"
                                    if d_info and d_info.city
                                    else dest
                                )
                                total_on_od = od_total_counts.get((orig, dest), 0)
                                share = (
                                    100 * cnt / total_on_od if total_on_od > 0 else 0
                                )
                                od_rows.append(
                                    {
                                        "Route": f"{o_lbl} → {d_lbl}",
                                        "Flights": cnt,
                                        "Total on route": total_on_od,
                                        "Share (%)": round(share, 1),
                                    }
                                )
                            od_df = pd.DataFrame(
                                od_rows,
                                columns=[
                                    "Route",
                                    "Flights",
                                    "Total on route",
                                    "Share (%)",
                                ],
                            )
                            if not od_df.empty:
                                fig_od = px.bar(
                                    od_df,
                                    x="Flights",
                                    y="Route",
                                    orientation="h",
                                    color="Share (%)",
                                    color_continuous_scale="Viridis",
                                    range_color=[0, 100],
                                    labels={"Flights": "Number of flights"},
                                    text=od_df["Share (%)"].apply(lambda x: f"{x}%"),
                                    custom_data=[
                                        "Flights",
                                        "Total on route",
                                        "Share (%)",
                                    ],
                                )
                                fig_od.update_traces(
                                    textposition="outside",
                                    hovertemplate="%{y}<br>Flights: %{customdata[0]:,}<br>Total on route: %{customdata[1]:,}<br>Airline share: %{customdata[2]}%<extra></extra>",
                                )
                                fig_od.update_layout(
                                    height=300 + od_n * 14,
                                    yaxis={"categoryorder": "total ascending"},
                                    showlegend=False,
                                )
                                _start_flight_count_axis_at_zero(fig_od, "x")
                                st.plotly_chart(fig_od, width="stretch")
                                st.dataframe(od_df, use_container_width=True)
                        else:
                            route_n = min(top_n, len(dest_counts_airline))
                            total_dest_counts = get_destination_column(
                                df, direction, focus_airport
                            ).value_counts()
                            route_rows_d: list[dict] = []
                            for iata, count in dest_counts_airline.head(
                                route_n
                            ).items():
                                info = get_airport(iata)
                                total_to_dest = total_dest_counts.get(iata, 0)
                                share = (
                                    100 * count / total_to_dest
                                    if total_to_dest > 0
                                    else 0
                                )
                                route_rows_d.append(
                                    {
                                        "Airport": iata,
                                        "Name": info.name if info else "",
                                        "City": info.city if info else "",
                                        "Country": info.country if info else "",
                                        "Flights": count,
                                        "Total": total_to_dest,
                                        "Share (%)": round(share, 1),
                                    }
                                )
                            route_df = pd.DataFrame(
                                route_rows_d,
                                columns=[
                                    "Airport",
                                    "Name",
                                    "City",
                                    "Country",
                                    "Flights",
                                    "Total",
                                    "Share (%)",
                                ],
                            )
                            if not route_df.empty:
                                route_df["Label"] = route_df.apply(
                                    lambda r: (
                                        f"{r['Airport']} - {r['Name']}"
                                        if r["Name"]
                                        else r["Airport"]
                                    ),
                                    axis=1,
                                )
                                fig_route = px.bar(
                                    route_df,
                                    x="Flights",
                                    y="Label",
                                    orientation="h",
                                    color="Share (%)",
                                    color_continuous_scale="Viridis",
                                    range_color=[0, 100],
                                    labels={
                                        "Flights": "Number of flights",
                                        "Share (%)": "Share (%)",
                                    },
                                    text=route_df["Share (%)"].apply(lambda x: f"{x}%"),
                                    custom_data=["Flights", "Total", "Share (%)"],
                                )
                                fig_route.update_traces(
                                    textposition="outside",
                                    hovertemplate="%{y}<br>Flights: %{customdata[0]:,}<br>Total: %{customdata[1]:,}<br>Share: %{customdata[2]}%<extra></extra>",
                                )
                                fig_route.update_layout(
                                    height=300 + route_n * 12,
                                    yaxis={"categoryorder": "total ascending"},
                                    showlegend=False,
                                )
                                _start_flight_count_axis_at_zero(fig_route, "x")
                                st.plotly_chart(fig_route, width="stretch")

                                top_dests = set(dest_counts_airline.head(route_n).index)
                                by_date_dest = (
                                    df_airline.assign(route_dest=route_dest_airline)
                                    .groupby([df_airline["date"].dt.date, "route_dest"])
                                    .size()
                                    .reset_index(name="Flights")
                                )
                                by_date_dest.columns = ["Date", "route_dest", "Flights"]
                                by_date_dest = by_date_dest[
                                    by_date_dest["route_dest"].isin(top_dests)
                                ]
                                if direction == "Departures":
                                    dest_col_df = df["destination"]
                                elif direction == "Arrivals":
                                    dest_col_df = df["origin"]
                                else:
                                    dest_col_df = pd.Series(
                                        np.where(
                                            df["origin"] == focus_airport,
                                            df["destination"],
                                            df["origin"],
                                        ),
                                        index=df.index,
                                    )
                                total_by_date_dest = (
                                    df.assign(route_dest=dest_col_df)
                                    .groupby([df["date"].dt.date, "route_dest"])
                                    .size()
                                    .reset_index(name="Total")
                                )
                                total_by_date_dest.columns = [
                                    "Date",
                                    "route_dest",
                                    "Total",
                                ]
                                by_date_dest = by_date_dest.merge(
                                    total_by_date_dest,
                                    on=["Date", "route_dest"],
                                    how="left",
                                )
                                by_date_dest["Share (%)"] = (
                                    100
                                    * by_date_dest["Flights"]
                                    / by_date_dest["Total"]
                                ).round(1)
                                by_date_dest["Route"] = by_date_dest[
                                    "route_dest"
                                ].apply(
                                    lambda iata: (
                                        get_airport(iata).name
                                        if get_airport(iata)
                                        else iata
                                    )
                                )
                                by_date_dest = _complete_daily_series(
                                    by_date_dest,
                                    date_col="Date",
                                    value_cols=["Flights", "Total", "Share (%)"],
                                    start_date=start_date,
                                    end_date=end_date,
                                    group_cols=["route_dest", "Route"],
                                )
                                if not by_date_dest.empty:
                                    fig_route_share_time = px.line(
                                        by_date_dest,
                                        x="Date",
                                        y="Share (%)",
                                        color="Route",
                                        labels={"Share (%)": "Share (%)"},
                                        custom_data=["Flights", "Total", "Route"],
                                    )
                                    fig_route_share_time.update_traces(
                                        hovertemplate="%{customdata[2]}<br>%{x}<br>Flights: %{customdata[0]:,}<br>Total (denom): %{customdata[1]:,}<br>Share: %{y}%<extra></extra>",
                                    )
                                    fig_route_share_time.update_layout(
                                        height=350,
                                        title="Share of traffic (%) over time by route",
                                        yaxis=dict(title="Share (%)"),
                                    )
                                    st.plotly_chart(
                                        fig_route_share_time, width="stretch"
                                    )

                                airline_flights_per_date = (
                                    df_airline.groupby(df_airline["date"].dt.date)
                                    .size()
                                    .rename("AirlineTotal")
                                )
                                by_date_dest_norm = (
                                    df_airline.assign(route_dest=route_dest_airline)
                                    .groupby([df_airline["date"].dt.date, "route_dest"])
                                    .size()
                                    .reset_index(name="Flights")
                                )
                                by_date_dest_norm.columns = [
                                    "Date",
                                    "route_dest",
                                    "Flights",
                                ]
                                by_date_dest_norm = by_date_dest_norm[
                                    by_date_dest_norm["route_dest"].isin(top_dests)
                                ]
                                by_date_dest_norm = by_date_dest_norm.merge(
                                    airline_flights_per_date,
                                    left_on="Date",
                                    right_index=True,
                                    how="left",
                                )
                                by_date_dest_norm["Norm (%)"] = (
                                    100
                                    * by_date_dest_norm["Flights"]
                                    / by_date_dest_norm["AirlineTotal"]
                                ).round(1)
                                by_date_dest_norm["Route"] = by_date_dest_norm[
                                    "route_dest"
                                ].apply(
                                    lambda iata: (
                                        get_airport(iata).name
                                        if get_airport(iata)
                                        else iata
                                    )
                                )
                                by_date_dest_norm = _complete_daily_series(
                                    by_date_dest_norm,
                                    date_col="Date",
                                    value_cols=["Flights", "AirlineTotal", "Norm (%)"],
                                    start_date=start_date,
                                    end_date=end_date,
                                    group_cols=["route_dest", "Route"],
                                )
                                if not by_date_dest_norm.empty:
                                    fig_route_norm = px.line(
                                        by_date_dest_norm,
                                        x="Date",
                                        y="Norm (%)",
                                        color="Route",
                                        labels={
                                            "Norm (%)": "Share of airline flights (%)"
                                        },
                                        custom_data=[
                                            "Flights",
                                            "AirlineTotal",
                                            "Route",
                                        ],
                                    )
                                    fig_route_norm.update_traces(
                                        hovertemplate="%{customdata[2]}<br>%{x}<br>Flights: %{customdata[0]:,}<br>Airline total (denom): %{customdata[1]:,}<br>Norm: %{y}%<extra></extra>",
                                    )
                                    fig_route_norm.update_layout(
                                        height=350,
                                        title="Share of airline flights (%) over time by route",
                                        yaxis=dict(
                                            title="Share of airline flights (%)"
                                        ),
                                    )
                                    st.plotly_chart(fig_route_norm, width="stretch")

                            st.dataframe(
                                route_df[
                                    [
                                        "Airport",
                                        "Name",
                                        "City",
                                        "Country",
                                        "Flights",
                                        "Share (%)",
                                    ]
                                ]
                                if not route_df.empty
                                else pd.DataFrame()
                            )

                    with tab_time:
                        by_date = (
                            df_airline.groupby(df_airline["date"].dt.date)
                            .size()
                            .reset_index(name="Flights")
                        )
                        by_date.columns = ["Date", "Flights"]
                        if not by_date.empty:
                            total_by_date = (
                                df.groupby(df["date"].dt.date)
                                .size()
                                .reset_index(name="Total")
                            )
                            total_by_date.columns = ["Date", "Total"]
                            share_df = by_date.merge(
                                total_by_date, on="Date", how="left"
                            )
                            share_df["Share"] = (
                                100 * share_df["Flights"] / share_df["Total"]
                            ).fillna(0)
                            share_df = _complete_daily_series(
                                share_df,
                                date_col="Date",
                                value_cols=["Flights", "Total", "Share"],
                                start_date=start_date,
                                end_date=end_date,
                            )

                            fig_time = go.Figure()
                            fig_time.add_trace(
                                go.Scatter(
                                    x=share_df["Date"],
                                    y=share_df["Flights"],
                                    name="Flights",
                                    line=dict(color="#1f77b4"),
                                    mode="lines",
                                )
                            )
                            fig_time.add_trace(
                                go.Scatter(
                                    x=share_df["Date"],
                                    y=share_df["Share"],
                                    name="Share of traffic (%)",
                                    yaxis="y2",
                                    line=dict(color="#ff7f0e"),
                                    mode="lines",
                                )
                            )
                            fig_time.update_layout(
                                height=350,
                                xaxis=dict(title="Date"),
                                yaxis=dict(title="Number of flights", side="left"),
                                yaxis2=dict(
                                    title="Share of traffic (%)",
                                    side="right",
                                    overlaying="y",
                                    range=[0, 100],
                                ),
                                legend=dict(x=1.1, xanchor="left"),
                            )
                            _start_flight_count_axis_at_zero(fig_time, "y")
                            st.plotly_chart(fig_time, width="stretch")

                            if not global_mode:
                                top_dests_time = set(
                                    dest_counts_airline.head(top_n).index
                                )
                                by_date_dest_time = (
                                    df_airline.assign(route_dest=route_dest_airline)
                                    .groupby([df_airline["date"].dt.date, "route_dest"])
                                    .size()
                                    .reset_index(name="Flights")
                                )
                                by_date_dest_time.columns = [
                                    "Date",
                                    "route_dest",
                                    "Flights",
                                ]
                                by_date_dest_time = by_date_dest_time[
                                    by_date_dest_time["route_dest"].isin(top_dests_time)
                                ]
                                by_date_dest_time = by_date_dest_time.merge(
                                    total_by_date_dest[["Date", "route_dest", "Total"]],
                                    on=["Date", "route_dest"],
                                    how="left",
                                )
                                by_date_dest_time["Route"] = by_date_dest_time[
                                    "route_dest"
                                ].apply(
                                    lambda iata: (
                                        get_airport(iata).name
                                        if get_airport(iata)
                                        else iata
                                    )
                                )
                                by_date_dest_time = _complete_daily_series(
                                    by_date_dest_time,
                                    date_col="Date",
                                    value_cols=["Flights", "Total"],
                                    start_date=start_date,
                                    end_date=end_date,
                                    group_cols=["route_dest", "Route"],
                                )
                                if not by_date_dest_time.empty:
                                    fig_route_count_time = px.line(
                                        by_date_dest_time,
                                        x="Date",
                                        y="Flights",
                                        color="Route",
                                        labels={"Flights": "Number of flights"},
                                        custom_data=["Total", "Route"],
                                    )
                                    fig_route_count_time.update_traces(
                                        hovertemplate="%{customdata[1]}<br>%{x}<br>Flights: %{y:,}<br>Total (denom): %{customdata[0]:,}<extra></extra>",
                                    )
                                    fig_route_count_time.update_layout(
                                        height=350,
                                        title="Flights over time by route",
                                    )
                                    _start_flight_count_axis_at_zero(
                                        fig_route_count_time, "y"
                                    )
                                    st.plotly_chart(
                                        fig_route_count_time, width="stretch"
                                    )
                        else:
                            st.caption("No date data.")

                    with tab_hour:
                        if not global_mode:
                            st.caption(
                                f"Departure time for flights from {focus_airport}; "
                                f"arrival time for flights to {focus_airport}."
                            )
                        if "scheduled_time" in df_airline.columns:
                            df_airline_hour = df_airline.dropna(
                                subset=["scheduled_time"]
                            )
                            df_airline_hour = df_airline_hour.copy()
                            df_airline_hour["hour"] = pd.to_datetime(
                                df_airline_hour["scheduled_time"], errors="coerce"
                            ).dt.hour
                            df_airline_hour = df_airline_hour.dropna(subset=["hour"])
                            by_hour = (
                                df_airline_hour.groupby("hour")
                                .size()
                                .reset_index(name="Flights")
                            )
                            if not by_hour.empty:
                                fig_hour = px.bar(
                                    by_hour,
                                    x="hour",
                                    y="Flights",
                                    labels={
                                        "hour": "Hour of day",
                                        "Flights": "Number of flights",
                                    },
                                )
                                fig_hour.update_layout(height=350)
                                _start_flight_count_axis_at_zero(fig_hour, "y")
                                st.plotly_chart(fig_hour, width="stretch")
                            else:
                                st.caption("No scheduled time data for this airline.")
                        else:
                            st.caption("No scheduled_time column in data.")

                    with tab_weekday:
                        _weekday_order = [
                            "Monday",
                            "Tuesday",
                            "Wednesday",
                            "Thursday",
                            "Friday",
                            "Saturday",
                            "Sunday",
                        ]
                        _wd = df_airline.copy()
                        _wd["weekday"] = _wd["date"].dt.day_name()
                        _wd_total = _wd.groupby("weekday").size().rename("Total")
                        _wd_dates = (
                            _wd.groupby("weekday")["date"]
                            .apply(lambda s: s.dt.date.nunique())
                            .rename("Days")
                        )
                        _wd_df = pd.concat([_wd_total, _wd_dates], axis=1).reset_index()
                        _wd_df["Avg"] = (_wd_df["Total"] / _wd_df["Days"]).round(1)
                        _wd_df["weekday"] = pd.Categorical(
                            _wd_df["weekday"], categories=_weekday_order, ordered=True
                        )
                        _wd_df = _wd_df.sort_values("weekday")
                        if not _wd_df.empty:
                            fig_wd = px.bar(
                                _wd_df,
                                x="weekday",
                                y="Avg",
                                labels={
                                    "weekday": "Day of week",
                                    "Avg": "Avg flights per day",
                                },
                                custom_data=["Total", "Days"],
                            )
                            fig_wd.update_traces(
                                hovertemplate="%{x}<br>Avg: %{y}<br>Total: %{customdata[0]:,}<br>Days: %{customdata[1]}<extra></extra>",
                            )
                            fig_wd.update_layout(height=350)
                            _start_flight_count_axis_at_zero(fig_wd, "y")
                            st.plotly_chart(fig_wd, width="stretch")
                        else:
                            st.caption("No date data for weekday analysis.")

                    if tab_cargo is not None:
                        with tab_cargo:
                            if "cargo" in df_airline.columns:
                                cargo_by_date = (
                                    df_airline.groupby(
                                        [df_airline["date"].dt.date, "cargo"]
                                    )
                                    .size()
                                    .reset_index(name="Flights")
                                )
                                cargo_by_date["Type"] = cargo_by_date["cargo"].map(
                                    {True: "Cargo", False: "Passenger"}
                                )
                                cargo_by_date = _complete_daily_series(
                                    cargo_by_date,
                                    date_col="date",
                                    value_cols=["Flights"],
                                    start_date=start_date,
                                    end_date=end_date,
                                    group_cols=["cargo", "Type"],
                                )
                                if not cargo_by_date.empty:
                                    fig_cargo = px.line(
                                        cargo_by_date,
                                        x="date",
                                        y="Flights",
                                        color="Type",
                                        labels={
                                            "date": "Date",
                                            "Flights": "Number of flights",
                                        },
                                        custom_data=["Type"],
                                    )
                                    fig_cargo.update_traces(
                                        hovertemplate="%{customdata[0]}<br>%{x}<br>Flights: %{y:,}<extra></extra>",
                                    )
                                    fig_cargo.update_layout(height=350)
                                    _start_flight_count_axis_at_zero(fig_cargo, "y")
                                    st.plotly_chart(fig_cargo, width="stretch")
                                cargo_passenger = (df_airline["cargo"] == False).sum()
                                cargo_cargo = (df_airline["cargo"] == True).sum()
                                cargo_df = pd.DataFrame(
                                    [
                                        {
                                            "Type": "Passenger",
                                            "Flights": cargo_passenger,
                                        },
                                        {"Type": "Cargo", "Flights": cargo_cargo},
                                    ]
                                )
                                st.dataframe(cargo_df)
                            else:
                                st.caption("No cargo column in data.")

                    with tab_map:
                        if global_mode:
                            _render_network_map(
                                df_airline,
                                airline_col,
                                [dive_icao],
                                geo_scope,
                                top_routes_n=top_n,
                            )
                        else:
                            if show_country:
                                map_point_by_dive = st.radio(
                                    "Map points by",
                                    options=["City (airport)", "Country"],
                                    index=1,
                                    horizontal=True,
                                    help="Show each destination as a precise city/airport, or aggregate by country.",
                                    key="airline_dive_map_by",
                                )
                            else:
                                map_point_by_dive = "City (airport)"
                            map_by_country_dive = map_point_by_dive == "Country"
                            _render_flight_map(
                                df_airline,
                                direction,
                                focus_airport,
                                focus_lat,
                                focus_lon,
                                map_by_country_dive,
                                [dive_icao],
                                airline_col,
                                geo_scope,
                                use_traffic_colors=True,
                                top_arcs_n=top_n,
                            )

        # ── Airline comparison ──
        st.header("Airline comparison")
        if not dive_airline_options:
            st.info("No airlines in the filtered data.")
        else:
            sel_cmp_airlines = st.multiselect(
                "Select airlines to compare",
                options=dive_airline_options,
                default=[],
                help="Pick 2 or more airlines to compare side by side.",
                key="airline_cmp_select",
            )
            cmp_codes = [dive_display_to_code.get(d, "") for d in sel_cmp_airlines]
            cmp_codes = [c for c in cmp_codes if c]

            if len(cmp_codes) < 2:
                st.info("Select at least 2 airlines to compare.")
            else:
                cmp_names: dict[str, str] = {}
                for code in cmp_codes:
                    a_info = get_airline(code)
                    cmp_names[code] = a_info.name if a_info else code

                summary_rows = []
                for code in cmp_codes:
                    df_a = df[df[airline_col] == code]
                    n = len(df_a)
                    share = 100 * n / total_flights if total_flights > 0 else 0
                    n_dests = get_destination_column(
                        df_a, direction, focus_airport
                    ).nunique()
                    pax = int((~df_a["cargo"]).sum()) if "cargo" in df_a.columns else n
                    cargo_n = int(df_a["cargo"].sum()) if "cargo" in df_a.columns else 0
                    summary_rows.append(
                        {
                            "Airline": cmp_names[code],
                            "ICAO": code,
                            "Flights": n,
                            "Share (%)": round(share, 1),
                            "Destinations": n_dests,
                            "Passenger": pax,
                            "Cargo": cargo_n,
                        }
                    )
                summary_cmp_df = pd.DataFrame(summary_rows)
                st.dataframe(summary_cmp_df, width="stretch")

                df_cmp = df[df[airline_col].isin(cmp_codes)].copy()
                df_cmp["Airline"] = df_cmp[airline_col].map(cmp_names)

                _cmp_tab_names = [
                    "Top routes",
                    "Flights over time",
                    "Share of traffic over time",
                    "Flights by hour",
                ]
                if not is_us:
                    _cmp_tab_names.append("Cargo vs passenger")
                _cmp_tab_names.append("Interactive map")
                _cmp_tabs = st.tabs(_cmp_tab_names)
                if is_us:
                    (
                        tab_cmp_routes,
                        tab_cmp_time,
                        tab_cmp_share,
                        tab_cmp_hour,
                        tab_cmp_map,
                    ) = _cmp_tabs
                    tab_cmp_cargo = None
                else:
                    (
                        tab_cmp_routes,
                        tab_cmp_time,
                        tab_cmp_share,
                        tab_cmp_hour,
                        tab_cmp_cargo,
                        tab_cmp_map,
                    ) = _cmp_tabs

                with tab_cmp_routes:
                    if global_mode:
                        all_top_ods: set[tuple[str, str]] = set()
                        for code in cmp_codes:
                            df_a = df[df[airline_col] == code]
                            top_ods = (
                                df_a.groupby(["origin", "destination"])
                                .size()
                                .sort_values(ascending=False)
                                .head(top_n)
                                .index
                            )
                            all_top_ods.update(top_ods)
                        cmp_od_rows: list[dict] = []
                        for code in cmp_codes:
                            df_a = df[df[airline_col] == code]
                            od_counts_a = df_a.groupby(["origin", "destination"]).size()
                            for orig, dest in sorted(all_top_ods):
                                cnt = od_counts_a.get((orig, dest), 0)
                                o_info = get_airport(orig)
                                d_info = get_airport(dest)
                                o_lbl = (
                                    f"{orig} ({o_info.city})"
                                    if o_info and o_info.city
                                    else orig
                                )
                                d_lbl = (
                                    f"{dest} ({d_info.city})"
                                    if d_info and d_info.city
                                    else dest
                                )
                                cmp_od_rows.append(
                                    {
                                        "Route": f"{o_lbl}→{d_lbl}",
                                        "Airline": cmp_names[code],
                                        "Flights": cnt,
                                    }
                                )
                        cmp_od_df = pd.DataFrame(cmp_od_rows)
                        if not cmp_od_df.empty:
                            fig_cmp_routes = px.bar(
                                cmp_od_df,
                                x="Flights",
                                y="Route",
                                color="Airline",
                                orientation="h",
                                barmode="group",
                                labels={"Flights": "Number of flights"},
                            )
                            fig_cmp_routes.update_layout(
                                height=400 + len(all_top_ods) * 25,
                                yaxis={"categoryorder": "total ascending"},
                            )
                            _start_flight_count_axis_at_zero(fig_cmp_routes, "x")
                            st.plotly_chart(fig_cmp_routes, width="stretch")
                    else:
                        all_top_dests: set[str] = set()
                        for code in cmp_codes:
                            df_a = df[df[airline_col] == code]
                            top = (
                                get_destination_column(df_a, direction, focus_airport)
                                .value_counts()
                                .head(top_n)
                                .index
                            )
                            all_top_dests.update(top)

                        route_cmp_rows: list[dict] = []
                        for code in cmp_codes:
                            df_a = df[df[airline_col] == code]
                            dest_counts_a = get_destination_column(
                                df_a, direction, focus_airport
                            ).value_counts()
                            for iata in sorted(all_top_dests):
                                count = dest_counts_a.get(iata, 0)
                                apt_info = get_airport(iata)
                                label = (
                                    f"{iata} - {apt_info.name}"
                                    if apt_info and apt_info.name
                                    else iata
                                )
                                route_cmp_rows.append(
                                    {
                                        "Destination": label,
                                        "Airline": cmp_names[code],
                                        "Flights": count,
                                    }
                                )
                        route_cmp_df = pd.DataFrame(route_cmp_rows)
                        if not route_cmp_df.empty:
                            fig_cmp_routes = px.bar(
                                route_cmp_df,
                                x="Flights",
                                y="Destination",
                                color="Airline",
                                orientation="h",
                                barmode="group",
                                labels={"Flights": "Number of flights"},
                            )
                            fig_cmp_routes.update_layout(
                                height=400 + len(all_top_dests) * 25,
                                yaxis={"categoryorder": "total ascending"},
                            )
                            _start_flight_count_axis_at_zero(fig_cmp_routes, "x")
                            st.plotly_chart(fig_cmp_routes, width="stretch")

                with tab_cmp_time:
                    by_date_cmp = (
                        df_cmp.groupby([df_cmp["date"].dt.date, "Airline"])
                        .size()
                        .reset_index(name="Flights")
                    )
                    by_date_cmp.columns = ["Date", "Airline", "Flights"]
                    by_date_cmp = _complete_daily_series(
                        by_date_cmp,
                        date_col="Date",
                        value_cols=["Flights"],
                        start_date=start_date,
                        end_date=end_date,
                        group_cols=["Airline"],
                    )
                    if not by_date_cmp.empty:
                        fig_cmp_time = px.line(
                            by_date_cmp,
                            x="Date",
                            y="Flights",
                            color="Airline",
                            labels={"Flights": "Number of flights"},
                        )
                        fig_cmp_time.update_layout(height=400)
                        _start_flight_count_axis_at_zero(fig_cmp_time, "y")
                        st.plotly_chart(fig_cmp_time, width="stretch")
                    else:
                        st.caption("No date data.")

                with tab_cmp_share:
                    total_by_date_cmp = (
                        df.groupby(df["date"].dt.date).size().rename("Total")
                    )
                    share_cmp = (
                        df_cmp.groupby([df_cmp["date"].dt.date, "Airline"])
                        .size()
                        .reset_index(name="Flights")
                    )
                    share_cmp.columns = ["Date", "Airline", "Flights"]
                    share_cmp = share_cmp.merge(
                        total_by_date_cmp, left_on="Date", right_index=True, how="left"
                    )
                    share_cmp["Share (%)"] = (
                        100 * share_cmp["Flights"] / share_cmp["Total"]
                    ).round(1)
                    share_cmp = _complete_daily_series(
                        share_cmp,
                        date_col="Date",
                        value_cols=["Flights", "Total", "Share (%)"],
                        start_date=start_date,
                        end_date=end_date,
                        group_cols=["Airline"],
                    )
                    if not share_cmp.empty:
                        fig_cmp_share = px.line(
                            share_cmp,
                            x="Date",
                            y="Share (%)",
                            color="Airline",
                            labels={"Share (%)": "Share of traffic (%)"},
                            custom_data=["Flights", "Total"],
                        )
                        fig_cmp_share.update_traces(
                            hovertemplate="%{data.name}<br>%{x}<br>Flights: %{customdata[0]:,}<br>Total: %{customdata[1]:,}<br>Share: %{y}%<extra></extra>",
                        )
                        fig_cmp_share.update_layout(height=400)
                        st.plotly_chart(fig_cmp_share, width="stretch")
                    else:
                        st.caption("No date data.")

                with tab_cmp_hour:
                    if not global_mode:
                        st.caption(
                            f"Departure time for flights from {focus_airport}; "
                            f"arrival time for flights to {focus_airport}."
                        )
                    if "scheduled_time" in df_cmp.columns:
                        df_cmp_hour = df_cmp.dropna(subset=["scheduled_time"]).copy()
                        df_cmp_hour["hour"] = pd.to_datetime(
                            df_cmp_hour["scheduled_time"], errors="coerce"
                        ).dt.hour
                        df_cmp_hour = df_cmp_hour.dropna(subset=["hour"])
                        by_hour_cmp = (
                            df_cmp_hour.groupby(["hour", "Airline"])
                            .size()
                            .reset_index(name="Flights")
                        )
                        if not by_hour_cmp.empty:
                            fig_cmp_hour = px.bar(
                                by_hour_cmp,
                                x="hour",
                                y="Flights",
                                color="Airline",
                                barmode="group",
                                labels={
                                    "hour": "Hour of day",
                                    "Flights": "Number of flights",
                                },
                            )
                            fig_cmp_hour.update_layout(height=400)
                            _start_flight_count_axis_at_zero(fig_cmp_hour, "y")
                            st.plotly_chart(fig_cmp_hour, width="stretch")
                        else:
                            st.caption("No scheduled time data.")
                    else:
                        st.caption("No scheduled_time column in data.")

                if tab_cmp_cargo is not None:
                    with tab_cmp_cargo:
                        if "cargo" in df_cmp.columns:
                            cargo_cmp_rows = []
                            for code in cmp_codes:
                                df_a = df[df[airline_col] == code]
                                pax = (
                                    int((~df_a["cargo"]).sum())
                                    if "cargo" in df_a.columns
                                    else 0
                                )
                                cargo_n = (
                                    int(df_a["cargo"].sum())
                                    if "cargo" in df_a.columns
                                    else 0
                                )
                                cargo_cmp_rows.append(
                                    {
                                        "Airline": cmp_names[code],
                                        "Type": "Passenger",
                                        "Flights": pax,
                                    }
                                )
                                cargo_cmp_rows.append(
                                    {
                                        "Airline": cmp_names[code],
                                        "Type": "Cargo",
                                        "Flights": cargo_n,
                                    }
                                )
                            cargo_cmp_df = pd.DataFrame(cargo_cmp_rows)
                            if not cargo_cmp_df.empty:
                                fig_cmp_cargo = px.bar(
                                    cargo_cmp_df,
                                    x="Flights",
                                    y="Airline",
                                    color="Type",
                                    orientation="h",
                                    barmode="group",
                                    labels={"Flights": "Number of flights"},
                                )
                                fig_cmp_cargo.update_layout(
                                    height=200 + len(cmp_codes) * 60
                                )
                                _start_flight_count_axis_at_zero(fig_cmp_cargo, "x")
                                st.plotly_chart(fig_cmp_cargo, width="stretch")

                            cargo_time_parts = []
                            for code in cmp_codes:
                                df_a = df[df[airline_col] == code]
                                if "cargo" in df_a.columns:
                                    by_dt_cargo = (
                                        df_a.groupby([df_a["date"].dt.date, "cargo"])
                                        .size()
                                        .reset_index(name="Flights")
                                    )
                                    by_dt_cargo["Type"] = by_dt_cargo["cargo"].map(
                                        {True: "Cargo", False: "Passenger"}
                                    )
                                    by_dt_cargo["Label"] = (
                                        cmp_names[code] + " - " + by_dt_cargo["Type"]
                                    )
                                    cargo_time_parts.append(by_dt_cargo)
                            if cargo_time_parts:
                                cargo_time_df = pd.concat(
                                    cargo_time_parts, ignore_index=True
                                )
                                if not cargo_time_df.empty:
                                    cargo_time_df = _complete_daily_series(
                                        cargo_time_df,
                                        date_col="date",
                                        value_cols=["Flights"],
                                        start_date=start_date,
                                        end_date=end_date,
                                        group_cols=["cargo", "Type", "Label"],
                                    )
                                    fig_cmp_cargo_time = px.line(
                                        cargo_time_df,
                                        x="date",
                                        y="Flights",
                                        color="Label",
                                        labels={
                                            "date": "Date",
                                            "Flights": "Number of flights",
                                        },
                                    )
                                    fig_cmp_cargo_time.update_layout(height=400)
                                    _start_flight_count_axis_at_zero(
                                        fig_cmp_cargo_time, "y"
                                    )
                                    st.plotly_chart(fig_cmp_cargo_time, width="stretch")
                        else:
                            st.caption("No cargo column in data.")

                with tab_cmp_map:
                    if global_mode:
                        _render_network_map(
                            df_cmp,
                            airline_col,
                            cmp_codes,
                            geo_scope,
                            top_routes_n=top_n,
                        )
                    else:
                        if show_country:
                            map_point_by_cmp = st.radio(
                                "Map points by",
                                options=["City (airport)", "Country"],
                                index=1,
                                horizontal=True,
                                help="Show each destination as a precise city/airport, or aggregate by country.",
                                key="airline_cmp_map_by",
                            )
                        else:
                            map_point_by_cmp = "City (airport)"
                        map_by_country_cmp = map_point_by_cmp == "Country"
                        _render_flight_map(
                            df_cmp,
                            direction,
                            focus_airport,
                            focus_lat,
                            focus_lon,
                            map_by_country_cmp,
                            cmp_codes,
                            airline_col,
                            geo_scope,
                            top_arcs_n=top_n,
                        )

    # ══════════════════════════════════════════════════════════════════════
    #  ROUTE DEEP DIVE
    # ══════════════════════════════════════════════════════════════════════
    elif section == "Route deep dive":
        st.header("Route deep dive")

        route_mode_options = ["By airport", "By city"]
        if show_country:
            route_mode_options.append("By country")
        route_mode = st.radio(
            "Route by",
            options=route_mode_options,
            index=0,
            horizontal=True,
            help="Dive into a single airport route, group airports by city, or aggregate all routes to a country.",
            key="route_dive_by",
        )
        route_by_city = route_mode == "By city"
        route_by_country = route_mode == "By country"
        route_multi_airport_only = False
        if route_by_city:
            route_multi_airport_only = st.checkbox(
                "Only cities with multiple airports",
                value=False,
                help="Show only city routes where the displayed city has multiple airports in the filtered data.",
                key="route_dive_multi_airport_only",
            )

        route_display_options: list[str] = []
        route_str_to_airports: dict[str, tuple[str, str]] = {}
        route_str_to_city_keys: dict[str, tuple[RouteCityKey, RouteCityKey]] = {}
        route_str_to_country: dict[str, str] = {}
        if route_by_country:
            _route_dest_codes = get_destination_column(df, direction, focus_airport)
            _route_country_counts: dict[str, int] = {}
            _route_country_iatas: dict[str, set[str]] = {}
            for iata, count in _route_dest_codes.value_counts().items():
                info = get_airport(iata)
                country = info.country if info and info.country else iata
                _route_country_counts[country] = (
                    _route_country_counts.get(country, 0) + count
                )
                _route_country_iatas.setdefault(country, set()).add(iata)
            for country, count in sorted(
                _route_country_counts.items(), key=lambda x: -x[1]
            ):
                label = f"{country} - {count:,} flights"
                route_display_options.append(label)
                route_str_to_country[label] = country
        elif route_by_city:
            _route_city_counts: dict[tuple[RouteCityKey, RouteCityKey], int] = {}
            _route_city_iatas: dict[RouteCityKey, set[str]] = {}
            for origin, destination in df[["origin", "destination"]].itertuples(
                index=False
            ):
                origin_key = _airport_city_key(origin)
                destination_key = _airport_city_key(destination)
                _route_city_iatas.setdefault(origin_key, set()).add(origin)
                _route_city_iatas.setdefault(destination_key, set()).add(destination)
                city_pair = tuple(sorted((origin_key, destination_key)))
                _route_city_counts[city_pair] = _route_city_counts.get(city_pair, 0) + 1
            focus_city_key = _airport_city_key(focus_airport) if focus_airport else None
            for (city_a, city_b), count in sorted(
                _route_city_counts.items(), key=lambda x: -x[1]
            ):
                if route_multi_airport_only:
                    if focus_city_key and not global_mode:
                        if city_a == focus_city_key or city_b == focus_city_key:
                            other_city = city_b if city_a == focus_city_key else city_a
                            if len(_route_city_iatas.get(other_city, set())) < 2:
                                continue
                        elif (
                            len(_route_city_iatas.get(city_a, set())) < 2
                            and len(_route_city_iatas.get(city_b, set())) < 2
                        ):
                            continue
                    elif (
                        len(_route_city_iatas.get(city_a, set())) < 2
                        and len(_route_city_iatas.get(city_b, set())) < 2
                    ):
                        continue
                if global_mode or not focus_city_key:
                    label = (
                        f"{_city_key_display(city_a, _route_city_iatas.get(city_a))}"
                        f" ↔ {_city_key_display(city_b, _route_city_iatas.get(city_b))}"
                        f" — {count:,} flights"
                    )
                elif city_a == focus_city_key or city_b == focus_city_key:
                    other_city = city_b if city_a == focus_city_key else city_a
                    label = (
                        f"{_city_key_display(other_city, _route_city_iatas.get(other_city))}"
                        f" - {count:,} flights"
                    )
                else:
                    label = (
                        f"{_city_key_display(city_a, _route_city_iatas.get(city_a))}"
                        f" ↔ {_city_key_display(city_b, _route_city_iatas.get(city_b))}"
                        f" — {count:,} flights"
                    )
                route_display_options.append(label)
                route_str_to_city_keys[label] = (city_a, city_b)
        else:
            route_series = df["origin"] + "-" + df["destination"]
            route_pairs = route_series.apply(
                lambda s: "-".join(sorted(s.split("-", 1))) if "-" in s else s
            )
            route_counts = route_pairs.value_counts()
            for route_str, count in route_counts.items():
                parts = route_str.split("-", 1)
                if len(parts) == 2:
                    a, b = parts[0], parts[1]
                    if global_mode:
                        a_info = get_airport(a)
                        b_info = get_airport(b)
                        a_city = a_info.city if a_info and a_info.city else a
                        b_city = b_info.city if b_info and b_info.city else b
                        label = f"{a} ({a_city}) ↔ {b} ({b_city}) — {count:,} flights"
                    else:
                        other = b if a == focus_airport else a
                        info = get_airport(other)
                        name = info.name if info and info.name else other
                        label = f"{other} - {name} - {count:,} flights"
                    route_display_options.append(label)
                    route_str_to_airports[label] = (a, b)

        col_search_r, col_select_r = st.columns(2)
        with col_search_r:
            if route_by_country:
                route_search = st.text_input(
                    "Search routes by country name",
                    placeholder="e.g. Japan, United States",
                    help="Filter the route list by typing a country name.",
                    key="route_dive_search",
                )
            elif route_by_city:
                route_search = st.text_input(
                    "Search routes by city, country, or airport code",
                    placeholder="e.g. New York, Los Angeles, JFK",
                    help="Filter the route list by typing a city, country, or airport code.",
                    key="route_dive_search",
                )
            else:
                route_search = st.text_input(
                    "Search routes by airport code or name",
                    placeholder="e.g. LAX, Atlanta, SFO",
                    help="Filter the route list by typing airport code (IATA) or airport name.",
                    key="route_dive_search",
                )
        search_lower = route_search.strip().lower()
        if search_lower:
            filtered_routes = [
                r for r in route_display_options if search_lower in r.lower()
            ]
        else:
            filtered_routes = route_display_options

        if not filtered_routes:
            st.info(
                "No routes match your search."
                if search_lower
                else "No routes in the filtered data."
            )
        else:
            with col_select_r:
                sel_route_display = st.selectbox(
                    "Select route",
                    options=filtered_routes,
                    index=0,
                    help="Explore statistics for a route (both directions grouped).",
                )

            if route_by_country:
                sel_country = route_str_to_country.get(sel_route_display, "")
                country_iatas = _route_country_iatas.get(sel_country, set())
                mask_country = df["origin"].isin(country_iatas) | df[
                    "destination"
                ].isin(country_iatas)
                df_route = df[mask_country]
            elif route_by_city:
                city_a, city_b = route_str_to_city_keys.get(
                    sel_route_display, (("", ""), ("", ""))
                )
                _origin_city_keys = df["origin"].apply(_airport_city_key)
                _destination_city_keys = df["destination"].apply(_airport_city_key)
                mask_city_pair = (
                    (_origin_city_keys == city_a) & (_destination_city_keys == city_b)
                ) | ((_origin_city_keys == city_b) & (_destination_city_keys == city_a))
                df_route = df[mask_city_pair]
            else:
                airport_a, airport_b = route_str_to_airports.get(
                    sel_route_display, ("", "")
                )
                mask_both = (
                    (df["origin"] == airport_a) & (df["destination"] == airport_b)
                ) | ((df["origin"] == airport_b) & (df["destination"] == airport_a))
                df_route = df[mask_both]

            if df_route.empty:
                st.info("No flights for this route in the selected filters.")
            else:
                if route_by_country:
                    route_label = sel_country
                elif route_by_city:
                    if global_mode:
                        route_label = (
                            f"{_city_key_label(city_a)} ↔ {_city_key_label(city_b)}"
                        )
                    else:
                        focus_city_key = (
                            _airport_city_key(focus_airport) if focus_airport else None
                        )
                        if focus_city_key and (
                            city_a == focus_city_key or city_b == focus_city_key
                        ):
                            other_city = city_b if city_a == focus_city_key else city_a
                            route_label = _city_key_label(other_city)
                        else:
                            route_label = (
                                f"{_city_key_label(city_a)} ↔ {_city_key_label(city_b)}"
                            )
                    _selected_multi_airport_city_keys = [
                        city_key
                        for city_key in dict.fromkeys([city_a, city_b])
                        if len(_route_city_iatas.get(city_key, set())) >= 2
                    ]
                elif global_mode:
                    a_info = get_airport(airport_a)
                    b_info = get_airport(airport_b)
                    a_city = a_info.city if a_info and a_info.city else airport_a
                    b_city = b_info.city if b_info and b_info.city else airport_b
                    route_label = f"{airport_a} ({a_city}) ↔ {airport_b} ({b_city})"
                else:
                    other = airport_b if airport_a == focus_airport else airport_a
                    other_info = get_airport(other)
                    name = other_info.name if other_info and other_info.name else other
                    route_label = f"{other} - {name}"
                st.subheader(route_label)

                n_route = len(df_route)
                pct_route = 100 * n_route / total_flights if total_flights > 0 else 0
                m1, m2 = st.columns(2)
                with m1:
                    st.metric("Total flights on route", f"{n_route:,}")
                with m2:
                    st.metric("Share of traffic", f"{pct_route:.1f}%")

                _route_tab_names: list[str] = []
                if route_by_country:
                    _route_tab_names.append("Top cities")
                if route_by_city and _selected_multi_airport_city_keys:
                    _route_tab_names.append("Airport comparison")
                _route_tab_names += [
                    "Top airlines",
                    "Flights over time",
                    "Flights by hour",
                    "Flights by weekday",
                ]
                if not is_us:
                    _route_tab_names.append("Cargo vs passenger")
                _route_tabs = st.tabs(_route_tab_names)
                _idx = 0
                if route_by_country:
                    tab_route_cities = _route_tabs[_idx]
                    _idx += 1
                else:
                    tab_route_cities = None
                if route_by_city and _selected_multi_airport_city_keys:
                    tab_route_airport_compare = _route_tabs[_idx]
                    _idx += 1
                else:
                    tab_route_airport_compare = None
                tab_route_airlines = _route_tabs[_idx]
                _idx += 1
                tab_route_time = _route_tabs[_idx]
                _idx += 1
                tab_route_hour = _route_tabs[_idx]
                _idx += 1
                tab_route_weekday = _route_tabs[_idx]
                _idx += 1
                tab_route_cargo = _route_tabs[_idx] if not is_us else None

                if tab_route_cities is not None:
                    with tab_route_cities:
                        _city_dest_codes = get_destination_column(
                            df_route, direction, focus_airport
                        )
                        _city_dest_counts = _city_dest_codes.value_counts()
                        _city_n = min(top_n, len(_city_dest_counts))
                        _total_country = len(df_route)
                        _city_rows = []
                        for iata, count in _city_dest_counts.head(_city_n).items():
                            apt = get_airport(iata)
                            share = (
                                100 * count / _total_country
                                if _total_country > 0
                                else 0
                            )
                            _city_rows.append(
                                {
                                    "Airport": iata,
                                    "Name": apt.name if apt else "",
                                    "City": apt.city if apt else "",
                                    "Flights": count,
                                    "Share (%)": round(share, 1),
                                }
                            )
                        _city_df = pd.DataFrame(
                            _city_rows,
                            columns=["Airport", "Name", "City", "Flights", "Share (%)"],
                        )
                        if not _city_df.empty:
                            _city_df["Label"] = _city_df.apply(
                                lambda r: (
                                    f"{r['Airport']} - {r['Name']}"
                                    if r["Name"]
                                    else r["Airport"]
                                ),
                                axis=1,
                            )
                            fig_cities = px.bar(
                                _city_df,
                                x="Flights",
                                y="Label",
                                orientation="h",
                                color="Share (%)",
                                color_continuous_scale="Viridis",
                                range_color=[0, 100],
                                labels={
                                    "Flights": "Number of flights",
                                    "Share (%)": "Share (%)",
                                },
                                text=_city_df["Share (%)"].apply(lambda x: f"{x}%"),
                                custom_data=["Flights", "Share (%)"],
                            )
                            fig_cities.update_traces(
                                hovertemplate="%{y}<br>Flights: %{customdata[0]:,}<br>Share: %{customdata[1]}%<extra></extra>",
                                textposition="outside",
                            )
                            fig_cities.update_layout(
                                height=300 + _city_n * 12,
                                yaxis={"categoryorder": "total ascending"},
                                showlegend=False,
                            )
                            _start_flight_count_axis_at_zero(fig_cities, "x")
                            st.plotly_chart(fig_cities, width="stretch")

                            _top_city_iatas = set(_city_dest_counts.head(_city_n).index)
                            if global_mode or direction == "Departures":
                                _city_route_dest = df_route["destination"]
                            elif direction == "Arrivals":
                                _city_route_dest = df_route["origin"]
                            else:
                                _city_route_dest = pd.Series(
                                    np.where(
                                        df_route["origin"] == focus_airport,
                                        df_route["destination"],
                                        df_route["origin"],
                                    ),
                                    index=df_route.index,
                                )
                            _by_date_city = (
                                df_route.assign(route_dest=_city_route_dest)
                                .groupby([df_route["date"].dt.date, "route_dest"])
                                .size()
                                .reset_index(name="Flights")
                            )
                            _by_date_city.columns = ["Date", "route_dest", "Flights"]
                            _by_date_city = _by_date_city[
                                _by_date_city["route_dest"].isin(_top_city_iatas)
                            ]
                            _by_date_city["City"] = _by_date_city["route_dest"].apply(
                                lambda iata: (
                                    f"{iata} - {get_airport(iata).name}"
                                    if get_airport(iata)
                                    else iata
                                )
                            )
                            if not _by_date_city.empty:
                                _by_date_city = _complete_daily_series(
                                    _by_date_city,
                                    date_col="Date",
                                    value_cols=["Flights"],
                                    start_date=start_date,
                                    end_date=end_date,
                                    group_cols=["route_dest", "City"],
                                )
                                fig_city_time = px.line(
                                    _by_date_city,
                                    x="Date",
                                    y="Flights",
                                    color="City",
                                    labels={"Flights": "Number of flights"},
                                )
                                fig_city_time.update_layout(
                                    height=350,
                                    title="Flights over time by city",
                                )
                                _start_flight_count_axis_at_zero(fig_city_time, "y")
                                st.plotly_chart(fig_city_time, width="stretch")

                        st.dataframe(
                            _city_df[
                                ["Airport", "Name", "City", "Flights", "Share (%)"]
                            ]
                            if not _city_df.empty
                            else pd.DataFrame()
                        )

                if tab_route_airport_compare is not None:
                    with tab_route_airport_compare:
                        st.caption(
                            "Compare how flights are split across airports within the selected multi-airport cities."
                        )
                        _airport_compare_rows = []
                        for row in df_route.itertuples(index=False):
                            for city_key, airport in [
                                (_airport_city_key(row.origin), row.origin),
                                (_airport_city_key(row.destination), row.destination),
                            ]:
                                if city_key not in _selected_multi_airport_city_keys:
                                    continue
                                info = get_airport(airport)
                                _airport_compare_rows.append(
                                    {
                                        "Date": row.date.date(),
                                        "City": _city_key_label(city_key),
                                        "Airport": airport,
                                        "Name": info.name if info else airport,
                                        "Airline": getattr(row, airline_col),
                                    }
                                )
                        _airport_compare_df = pd.DataFrame(_airport_compare_rows)
                        if _airport_compare_df.empty:
                            st.caption(
                                "No multi-airport city traffic is available for this route."
                            )
                        else:
                            _airport_counts = (
                                _airport_compare_df.groupby(
                                    ["City", "Airport", "Name"], as_index=False
                                )
                                .size()
                                .rename(columns={"size": "Flights"})
                            )
                            _airport_counts["City total"] = _airport_counts.groupby(
                                "City"
                            )["Flights"].transform("sum")
                            _airport_counts["Share (%)"] = (
                                100
                                * _airport_counts["Flights"]
                                / _airport_counts["City total"]
                            ).round(1)
                            _airport_counts["Share label"] = _airport_counts[
                                "Share (%)"
                            ].apply(lambda x: f"{x}%")
                            _airport_counts["Label"] = (
                                _airport_counts["Airport"]
                                + " - "
                                + _airport_counts["Name"]
                            )
                            fig_airport_compare = px.bar(
                                _airport_counts.sort_values("Flights"),
                                x="Flights",
                                y="Label",
                                color="City",
                                orientation="h",
                                labels={"Flights": "Number of flights"},
                                text="Share label",
                                custom_data=["City", "Share (%)"],
                            )
                            fig_airport_compare.update_traces(
                                hovertemplate="%{customdata[0]}<br>%{y}<br>Flights: %{x:,}<br>City share: %{customdata[1]}%<extra></extra>",
                                textposition="outside",
                            )
                            fig_airport_compare.update_layout(
                                height=300 + len(_airport_counts) * 16,
                                yaxis={"categoryorder": "total ascending"},
                            )
                            _start_flight_count_axis_at_zero(fig_airport_compare, "x")
                            st.plotly_chart(fig_airport_compare, width="stretch")

                            _airport_daily = (
                                _airport_compare_df.groupby(
                                    ["Date", "City", "Airport"], as_index=False
                                )
                                .size()
                                .rename(columns={"size": "Flights"})
                            )
                            _airport_daily["Airport label"] = (
                                _airport_daily["City"]
                                + " | "
                                + _airport_daily["Airport"]
                            )
                            _airport_daily = _complete_daily_series(
                                _airport_daily,
                                date_col="Date",
                                value_cols=["Flights"],
                                start_date=start_date,
                                end_date=end_date,
                                group_cols=["City", "Airport", "Airport label"],
                            )
                            fig_airport_daily = px.line(
                                _airport_daily,
                                x="Date",
                                y="Flights",
                                color="Airport label",
                                labels={"Flights": "Number of flights"},
                            )
                            fig_airport_daily.update_layout(
                                height=350,
                                title="Flights over time by airport",
                            )
                            _start_flight_count_axis_at_zero(fig_airport_daily, "y")
                            st.plotly_chart(fig_airport_daily, width="stretch")

                            _airport_daily_share = _airport_daily.copy()
                            _airport_daily_share["City total"] = (
                                _airport_daily_share.groupby(["Date", "City"])[
                                    "Flights"
                                ].transform("sum")
                            )
                            _airport_daily_share["Share (%)"] = np.where(
                                _airport_daily_share["City total"] > 0,
                                100
                                * _airport_daily_share["Flights"]
                                / _airport_daily_share["City total"],
                                0,
                            ).round(1)
                            fig_airport_daily_share = px.line(
                                _airport_daily_share,
                                x="Date",
                                y="Share (%)",
                                color="Airport label",
                                labels={"Share (%)": "Share of city flights (%)"},
                                custom_data=["Flights", "City total"],
                            )
                            fig_airport_daily_share.update_traces(
                                hovertemplate="%{fullData.name}<br>%{x}<br>Flights: %{customdata[0]:,}<br>City total: %{customdata[1]:,}<br>Share: %{y}%<extra></extra>",
                            )
                            fig_airport_daily_share.update_layout(
                                height=350,
                                title="Share of city flights per day by airport",
                                yaxis=dict(
                                    title="Share of city flights (%)", range=[0, 100]
                                ),
                            )
                            st.plotly_chart(fig_airport_daily_share, width="stretch")

                            _airport_airline = (
                                _airport_compare_df.groupby(
                                    ["City", "Airport", "Airline"], as_index=False
                                )
                                .size()
                                .rename(columns={"size": "Flights"})
                            )
                            _airport_airline["Airline name"] = _airport_airline[
                                "Airline"
                            ].apply(
                                lambda c: get_airline(c).name if get_airline(c) else c
                            )
                            _airport_airline["Airport label"] = (
                                _airport_airline["City"]
                                + " | "
                                + _airport_airline["Airport"]
                            )
                            _airport_airline = _airport_airline.sort_values(
                                "Flights", ascending=False
                            ).head(top_n)
                            fig_airport_airline = px.bar(
                                _airport_airline,
                                x="Flights",
                                y="Airport label",
                                color="Airline name",
                                orientation="h",
                                labels={"Flights": "Number of flights"},
                            )
                            fig_airport_airline.update_layout(
                                height=300 + len(_airport_airline) * 12,
                                title="Top airline contributions by airport",
                                yaxis={"categoryorder": "total ascending"},
                            )
                            _start_flight_count_axis_at_zero(fig_airport_airline, "x")
                            st.plotly_chart(fig_airport_airline, width="stretch")

                            _airport_grid = _airport_counts[
                                [
                                    "City",
                                    "Airport",
                                    "Name",
                                    "Flights",
                                    "Share (%)",
                                ]
                            ]
                            gb = GridOptionsBuilder.from_dataframe(_airport_grid)
                            gb.configure_default_column(
                                sortable=True,
                                filter=True,
                                resizable=True,
                                flex=1,
                                minWidth=100,
                            )
                            grid_options = gb.build()
                            grid_options.pop("autoSizeStrategy", None)
                            AgGrid(
                                _airport_grid,
                                gridOptions=grid_options,
                                height=min(420, 80 + 35 * len(_airport_counts)),
                            )

                with tab_route_airlines:
                    airline_counts_route = df_route[airline_col].value_counts()
                    total_on_route = len(df_route)
                    airline_rows = []
                    for icao, count in airline_counts_route.head(top_n).items():
                        info = get_airline(icao)
                        name = info.name if info else icao
                        share = (
                            100 * count / total_on_route if total_on_route > 0 else 0
                        )
                        airline_rows.append(
                            {
                                "Airline": name,
                                "ICAO": icao,
                                "Flights": count,
                                "Share (%)": round(share, 1),
                            }
                        )
                    airline_route_df = pd.DataFrame(
                        airline_rows,
                        columns=["Airline", "ICAO", "Flights", "Share (%)"],
                    )
                    if not airline_route_df.empty:
                        fig_route_airlines = px.bar(
                            airline_route_df,
                            x="Flights",
                            y="Airline",
                            orientation="h",
                            color="Share (%)",
                            color_continuous_scale="Viridis",
                            range_color=[0, 100],
                            labels={
                                "Flights": "Number of flights",
                                "Share (%)": "Share (%)",
                            },
                            text=airline_route_df["Share (%)"].apply(lambda x: f"{x}%"),
                        )
                        fig_route_airlines.update_layout(
                            height=300 + min(top_n, len(airline_route_df)) * 12,
                            yaxis={"categoryorder": "total ascending"},
                            showlegend=False,
                        )
                        _start_flight_count_axis_at_zero(fig_route_airlines, "x")
                        fig_route_airlines.update_traces(textposition="outside")
                        st.plotly_chart(fig_route_airlines, width="stretch")

                        top_airlines_route = set(airline_counts_route.head(top_n).index)
                        by_date_airline = (
                            df_route.groupby([df_route["date"].dt.date, airline_col])
                            .size()
                            .reset_index(name="Flights")
                        )
                        by_date_airline.columns = ["Date", "ICAO", "Flights"]
                        total_per_date = df_route.groupby(
                            df_route["date"].dt.date
                        ).size()
                        by_date_airline = by_date_airline[
                            by_date_airline["ICAO"].isin(top_airlines_route)
                        ]
                        by_date_airline = by_date_airline.merge(
                            total_per_date.rename("Total"),
                            left_on="Date",
                            right_index=True,
                        )
                        by_date_airline["Share (%)"] = (
                            100 * by_date_airline["Flights"] / by_date_airline["Total"]
                        ).round(1)
                        by_date_airline["Airline"] = by_date_airline["ICAO"].apply(
                            lambda c: get_airline(c).name if get_airline(c) else c
                        )
                        if not by_date_airline.empty:
                            by_date_airline = _complete_daily_series(
                                by_date_airline,
                                date_col="Date",
                                value_cols=["Flights", "Total", "Share (%)"],
                                start_date=start_date,
                                end_date=end_date,
                                group_cols=["ICAO", "Airline"],
                            )
                            fig_share_day = px.line(
                                by_date_airline,
                                x="Date",
                                y="Share (%)",
                                color="Airline",
                                labels={"Share (%)": "Share (%)"},
                                custom_data=["Flights", "Total", "Airline"],
                            )
                            fig_share_day.update_traces(
                                hovertemplate="%{customdata[2]}<br>%{x}<br>Flights: %{customdata[0]:,}<br>Total (denom): %{customdata[1]:,}<br>Share: %{y}%<extra></extra>",
                            )
                            fig_share_day.update_layout(
                                height=350,
                                title="Share of traffic (%) over time by airline",
                                yaxis=dict(title="Share (%)"),
                            )
                            st.plotly_chart(fig_share_day, width="stretch")

                    st.dataframe(
                        airline_route_df[["Airline", "ICAO", "Flights", "Share (%)"]]
                        if not airline_route_df.empty
                        else pd.DataFrame()
                    )

                with tab_route_time:
                    by_date_route = (
                        df_route.groupby(df_route["date"].dt.date)
                        .size()
                        .reset_index(name="Flights")
                    )
                    by_date_route.columns = ["Date", "Flights"]
                    if not by_date_route.empty:
                        total_by_date = (
                            df.groupby(df["date"].dt.date)
                            .size()
                            .reset_index(name="Total")
                        )
                        total_by_date.columns = ["Date", "Total"]
                        share_route_df = by_date_route.merge(
                            total_by_date, on="Date", how="left"
                        )
                        share_route_df["Share"] = (
                            100 * share_route_df["Flights"] / share_route_df["Total"]
                        ).fillna(0)
                        share_route_df = _complete_daily_series(
                            share_route_df,
                            date_col="Date",
                            value_cols=["Flights", "Total", "Share"],
                            start_date=start_date,
                            end_date=end_date,
                        )

                        fig_route_time = go.Figure()
                        fig_route_time.add_trace(
                            go.Scatter(
                                x=share_route_df["Date"],
                                y=share_route_df["Flights"],
                                name="Flights",
                                line=dict(color="#1f77b4"),
                                mode="lines",
                            )
                        )
                        fig_route_time.add_trace(
                            go.Scatter(
                                x=share_route_df["Date"],
                                y=share_route_df["Share"],
                                name="Share of traffic (%)",
                                yaxis="y2",
                                line=dict(color="#ff7f0e"),
                                mode="lines",
                            )
                        )
                        fig_route_time.update_layout(
                            height=350,
                            xaxis=dict(title="Date"),
                            yaxis=dict(title="Number of flights", side="left"),
                            yaxis2=dict(
                                title="Share of traffic (%)",
                                side="right",
                                overlaying="y",
                                range=[0, 100],
                            ),
                            legend=dict(x=1.1, xanchor="left"),
                        )
                        _start_flight_count_axis_at_zero(fig_route_time, "y")
                        st.plotly_chart(fig_route_time, width="stretch")

                        top_airlines_route = set(airline_counts_route.head(top_n).index)
                        by_date_airline_time = (
                            df_route.groupby([df_route["date"].dt.date, airline_col])
                            .size()
                            .reset_index(name="Flights")
                        )
                        by_date_airline_time.columns = ["Date", "ICAO", "Flights"]
                        by_date_airline_time = by_date_airline_time[
                            by_date_airline_time["ICAO"].isin(top_airlines_route)
                        ]
                        total_per_date_route = (
                            df_route.groupby(df_route["date"].dt.date)
                            .size()
                            .rename("Total")
                        )
                        by_date_airline_time = by_date_airline_time.merge(
                            total_per_date_route,
                            left_on="Date",
                            right_index=True,
                            how="left",
                        )
                        by_date_airline_time["Airline"] = by_date_airline_time[
                            "ICAO"
                        ].apply(lambda c: get_airline(c).name if get_airline(c) else c)
                        by_date_airline_time = _complete_daily_series(
                            by_date_airline_time,
                            date_col="Date",
                            value_cols=["Flights", "Total"],
                            start_date=start_date,
                            end_date=end_date,
                            group_cols=["ICAO", "Airline"],
                        )
                        if not by_date_airline_time.empty:
                            fig_count_day = px.line(
                                by_date_airline_time,
                                x="Date",
                                y="Flights",
                                color="Airline",
                                labels={"Flights": "Number of flights"},
                                custom_data=["Total", "Airline"],
                            )
                            fig_count_day.update_traces(
                                hovertemplate="%{customdata[1]}<br>%{x}<br>Flights: %{y:,}<br>Total (denom): %{customdata[0]:,}<extra></extra>",
                            )
                            fig_count_day.update_layout(
                                height=350,
                                title="Flights over time by airline",
                            )
                            _start_flight_count_axis_at_zero(fig_count_day, "y")
                            st.plotly_chart(fig_count_day, width="stretch")
                    else:
                        st.caption("No date data.")

                with tab_route_hour:
                    if not global_mode:
                        st.caption(
                            f"Departure time for flights from {focus_airport}; "
                            f"arrival time for flights to {focus_airport}."
                        )
                    if "scheduled_time" in df_route.columns:
                        df_route_hour = df_route.dropna(subset=["scheduled_time"])
                        df_route_hour = df_route_hour.copy()
                        df_route_hour["hour"] = pd.to_datetime(
                            df_route_hour["scheduled_time"], errors="coerce"
                        ).dt.hour
                        df_route_hour = df_route_hour.dropna(subset=["hour"])
                        by_hour_route = (
                            df_route_hour.groupby("hour")
                            .size()
                            .reset_index(name="Flights")
                        )
                        if not by_hour_route.empty:
                            fig_route_hour = px.bar(
                                by_hour_route,
                                x="hour",
                                y="Flights",
                                labels={
                                    "hour": "Hour of day",
                                    "Flights": "Number of flights",
                                },
                            )
                            fig_route_hour.update_layout(height=350)
                            _start_flight_count_axis_at_zero(fig_route_hour, "y")
                            st.plotly_chart(fig_route_hour, width="stretch")
                        else:
                            st.caption("No scheduled time data for this route.")
                    else:
                        st.caption("No scheduled_time column in data.")

                with tab_route_weekday:
                    _rwd_order = [
                        "Monday",
                        "Tuesday",
                        "Wednesday",
                        "Thursday",
                        "Friday",
                        "Saturday",
                        "Sunday",
                    ]
                    _rwd = df_route.copy()
                    _rwd["weekday"] = _rwd["date"].dt.day_name()
                    _rwd_total = _rwd.groupby("weekday").size().rename("Total")
                    _rwd_dates = (
                        _rwd.groupby("weekday")["date"]
                        .apply(lambda s: s.dt.date.nunique())
                        .rename("Days")
                    )
                    _rwd_df = pd.concat([_rwd_total, _rwd_dates], axis=1).reset_index()
                    _rwd_df["Avg"] = (_rwd_df["Total"] / _rwd_df["Days"]).round(1)
                    _rwd_df["weekday"] = pd.Categorical(
                        _rwd_df["weekday"], categories=_rwd_order, ordered=True
                    )
                    _rwd_df = _rwd_df.sort_values("weekday")
                    if not _rwd_df.empty:
                        fig_rwd = px.bar(
                            _rwd_df,
                            x="weekday",
                            y="Avg",
                            labels={
                                "weekday": "Day of week",
                                "Avg": "Avg flights per day",
                            },
                            custom_data=["Total", "Days"],
                        )
                        fig_rwd.update_traces(
                            hovertemplate="%{x}<br>Avg: %{y}<br>Total: %{customdata[0]:,}<br>Days: %{customdata[1]}<extra></extra>",
                        )
                        fig_rwd.update_layout(height=350)
                        _start_flight_count_axis_at_zero(fig_rwd, "y")
                        st.plotly_chart(fig_rwd, width="stretch")
                    else:
                        st.caption("No date data for weekday analysis.")

                if tab_route_cargo is not None:
                    with tab_route_cargo:
                        if "cargo" in df_route.columns:
                            cargo_by_date_route = (
                                df_route.groupby([df_route["date"].dt.date, "cargo"])
                                .size()
                                .reset_index(name="Flights")
                            )
                            cargo_by_date_route["Type"] = cargo_by_date_route[
                                "cargo"
                            ].map({True: "Cargo", False: "Passenger"})
                            cargo_by_date_route = _complete_daily_series(
                                cargo_by_date_route,
                                date_col="date",
                                value_cols=["Flights"],
                                start_date=start_date,
                                end_date=end_date,
                                group_cols=["cargo", "Type"],
                            )
                            if not cargo_by_date_route.empty:
                                fig_route_cargo = px.line(
                                    cargo_by_date_route,
                                    x="date",
                                    y="Flights",
                                    color="Type",
                                    labels={
                                        "date": "Date",
                                        "Flights": "Number of flights",
                                    },
                                    custom_data=["Type"],
                                )
                                fig_route_cargo.update_traces(
                                    hovertemplate="%{customdata[0]}<br>%{x}<br>Flights: %{y:,}<extra></extra>",
                                )
                                fig_route_cargo.update_layout(height=350)
                                _start_flight_count_axis_at_zero(fig_route_cargo, "y")
                                st.plotly_chart(fig_route_cargo, width="stretch")
                            cargo_passenger_r = (df_route["cargo"] == False).sum()
                            cargo_cargo_r = (df_route["cargo"] == True).sum()
                            cargo_route_df = pd.DataFrame(
                                [
                                    {"Type": "Passenger", "Flights": cargo_passenger_r},
                                    {"Type": "Cargo", "Flights": cargo_cargo_r},
                                ]
                            )
                            st.dataframe(cargo_route_df)
                        else:
                            st.caption("No cargo column in data.")

    # ══════════════════════════════════════════════════════════════════════
    #  DELAY ANALYSIS (US-specific)
    # ══════════════════════════════════════════════════════════════════════
    elif section == "Delay analysis":
        st.header("Delay analysis")
        if global_mode:
            st.caption("Analyzing arrival delays for all US domestic flights")
        else:
            st.caption(f"Analyzing arrival delays for flights involving {focus_label}")

        df_delay = df.copy()
        df_delay["delay_min"] = df_delay["status"].apply(parse_delay_minutes)

        n_total = len(df_delay)
        df_with_delay = df_delay.dropna(subset=["delay_min"])
        n_arrived = len(df_with_delay)
        n_cancelled = n_total - n_arrived
        n_on_time = int((df_with_delay["delay_min"] == 0).sum())
        n_delayed = int((df_with_delay["delay_min"] > 0).sum())
        avg_delay_val = df_with_delay.loc[
            df_with_delay["delay_min"] > 0, "delay_min"
        ].mean()

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            on_time_pct = 100 * n_on_time / n_arrived if n_arrived > 0 else 0
            st.metric("On-time (%)", f"{on_time_pct:.1f}%")
        with c2:
            delayed_pct = 100 * n_delayed / n_arrived if n_arrived > 0 else 0
            st.metric("Delayed (%)", f"{delayed_pct:.1f}%")
        with c3:
            st.metric("Cancelled / diverted", f"{n_cancelled:,}")
        with c4:
            st.metric(
                "Avg delay (when late)",
                f"{avg_delay_val:.0f} min" if not pd.isna(avg_delay_val) else "N/A",
            )

        # ── Delay distribution ──
        st.subheader("Delay distribution")
        delayed_flights = df_with_delay[df_with_delay["delay_min"] > 0]
        if not delayed_flights.empty:
            fig_delay_hist = px.histogram(
                delayed_flights,
                x="delay_min",
                nbins=50,
                labels={"delay_min": "Delay (minutes)", "count": "Flights"},
            )
            fig_delay_hist.update_layout(height=350, showlegend=False)
            _start_flight_count_axis_at_zero(fig_delay_hist, "y")
            st.plotly_chart(fig_delay_hist, width="stretch")
        else:
            st.caption("No delayed flights in the selected filters.")

        # ── On-time performance by airline ──
        st.subheader("On-time performance by airline")
        airline_delay = (
            df_with_delay.groupby(airline_col)["delay_min"]
            .agg(
                total="count",
                on_time=lambda x: int((x == 0).sum()),
                avg_delay=lambda x: x[x > 0].mean(),
                delayed_15=lambda x: int((x >= 15).sum()),
            )
            .reset_index()
        )
        airline_delay.columns = [
            airline_col,
            "Total",
            "On-time",
            "Avg delay (min)",
            "Delayed 15+ min",
        ]
        airline_delay["On-time (%)"] = (
            100 * airline_delay["On-time"] / airline_delay["Total"]
        ).round(1)
        airline_delay = airline_delay.sort_values("Total", ascending=False).head(top_n)
        airline_delay["Airline"] = airline_delay[airline_col].apply(
            lambda c: get_airline(c).name if get_airline(c) else c
        )

        if not airline_delay.empty:
            plot_df = airline_delay.sort_values("On-time (%)", ascending=True)
            fig_otp = px.bar(
                plot_df,
                x="On-time (%)",
                y="Airline",
                orientation="h",
                color="On-time (%)",
                color_continuous_scale="RdYlGn",
                range_color=[50, 100],
                text=plot_df["On-time (%)"].apply(lambda x: f"{x}%"),
                custom_data=["Total", "Avg delay (min)"],
            )
            fig_otp.update_traces(
                textposition="outside",
                hovertemplate="%{y}<br>On-time: %{x}%<br>Total flights: %{customdata[0]:,}<br>Avg delay: %{customdata[1]:.0f} min<extra></extra>",
            )
            fig_otp.update_layout(height=320, showlegend=False)
            st.plotly_chart(fig_otp, width="stretch")

        # ── Average delay by hour ──
        st.subheader("Average delay by hour of day")
        if "scheduled_time" in df_with_delay.columns:
            df_hour_delay = df_with_delay.copy()
            df_hour_delay["hour"] = pd.to_datetime(
                df_hour_delay["scheduled_time"], errors="coerce"
            ).dt.hour
            df_hour_delay = df_hour_delay.dropna(subset=["hour"])
            by_hour_d = (
                df_hour_delay.groupby("hour")["delay_min"]
                .agg(
                    avg_delay="mean",
                    on_time_pct=lambda x: 100 * (x == 0).sum() / len(x),
                    total="count",
                )
                .reset_index()
            )
            by_hour_d.columns = ["Hour", "Avg delay (min)", "On-time (%)", "Total"]
            if not by_hour_d.empty:
                fig_hour_delay = go.Figure()
                fig_hour_delay.add_trace(
                    go.Bar(
                        x=by_hour_d["Hour"],
                        y=by_hour_d["Avg delay (min)"],
                        name="Avg delay (min)",
                    )
                )
                fig_hour_delay.add_trace(
                    go.Scatter(
                        x=by_hour_d["Hour"],
                        y=by_hour_d["On-time (%)"],
                        name="On-time (%)",
                        yaxis="y2",
                        line=dict(color="#ff7f0e"),
                        mode="lines",
                    )
                )
                fig_hour_delay.update_layout(
                    height=350,
                    xaxis=dict(title="Hour of day"),
                    yaxis=dict(title="Avg delay (min)", side="left"),
                    yaxis2=dict(
                        title="On-time (%)",
                        side="right",
                        overlaying="y",
                        range=[0, 100],
                    ),
                    legend=dict(x=1.1, xanchor="left"),
                )
                st.plotly_chart(fig_hour_delay, width="stretch")

        # ── On-time performance over time ──
        st.subheader("On-time performance over time")
        delay_by_date = (
            df_with_delay.groupby(df_with_delay["date"].dt.date)["delay_min"]
            .agg(
                on_time_pct=lambda x: 100 * (x == 0).sum() / len(x),
                avg_delay="mean",
                total="count",
            )
            .reset_index()
        )
        delay_by_date.columns = ["Date", "On-time (%)", "Avg delay (min)", "Total"]
        delay_by_date = _complete_daily_series(
            delay_by_date,
            date_col="Date",
            value_cols=["On-time (%)", "Avg delay (min)", "Total"],
            start_date=start_date,
            end_date=end_date,
        )
        if not delay_by_date.empty:
            fig_delay_time = go.Figure()
            fig_delay_time.add_trace(
                go.Scatter(
                    x=delay_by_date["Date"],
                    y=delay_by_date["On-time (%)"],
                    name="On-time (%)",
                    line=dict(color="#2ca02c"),
                    mode="lines",
                )
            )
            fig_delay_time.add_trace(
                go.Scatter(
                    x=delay_by_date["Date"],
                    y=delay_by_date["Avg delay (min)"],
                    name="Avg delay (min)",
                    yaxis="y2",
                    line=dict(color="#d62728"),
                    mode="lines",
                )
            )
            fig_delay_time.update_layout(
                height=350,
                xaxis=dict(title="Date"),
                yaxis=dict(title="On-time (%)", side="left", range=[0, 100]),
                yaxis2=dict(
                    title="Avg delay (min)",
                    side="right",
                    overlaying="y",
                ),
                legend=dict(x=1.1, xanchor="left"),
            )
            st.plotly_chart(fig_delay_time, width="stretch")


if __name__ == "__main__":
    main()
