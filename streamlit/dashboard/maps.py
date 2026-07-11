"""Map rendering helpers."""

from collections.abc import Sequence

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from flyghts.reference import get_airline, get_airport

from .charts import _complete_daily_series, _start_flight_count_axis_at_zero
from .components import _render_aggrid
from .data import build_map_points, get_destination_column


def _get_map_layout_opts(
    scope: str = "world", center: tuple[float, float] | None = None
) -> dict:
    """Return OpenStreetMap layout options parameterized by scope."""
    opts: dict = {"style": "open-street-map"}
    if center is not None:
        opts["center"] = {"lat": center[0], "lon": center[1]}
        opts["zoom"] = 3 if scope == "usa" else 2
    elif scope == "usa":
        opts["center"] = {"lat": 39.5, "lon": -98}
        opts["zoom"] = 3
    else:
        opts["center"] = {"lat": 20, "lon": 0}
        opts["zoom"] = 1
    return opts


def _map_center_zoom_from_coords(
    lats: Sequence[float],
    lons: Sequence[float],
    *,
    map_height_px: int = 600,
    map_width_px: float = 900,
    margin: float = 1.35,
) -> dict[str, object]:
    """Return center and zoom that initially frame coordinates without locking pan/zoom."""
    lat_min = float(min(lats))
    lat_max = float(max(lats))
    lon_min = float(min(lons))
    lon_max = float(max(lons))
    center = {
        "lat": (lat_min + lat_max) / 2,
        "lon": (lon_min + lon_max) / 2,
    }
    lat_span = max(lat_max - lat_min, 0.25) * margin
    lon_span = max(lon_max - lon_min, 0.25) * margin
    aspect = map_width_px / map_height_px
    lon_zoom_range = np.array(
        [
            0.0007,
            0.0014,
            0.003,
            0.006,
            0.012,
            0.024,
            0.048,
            0.096,
            0.192,
            0.3712,
            0.768,
            1.536,
            3.072,
            6.144,
            11.8784,
            23.7568,
            47.5136,
            98.304,
            190.0544,
            360.0,
        ]
    )
    zoom_levels = np.arange(20, 0, -1, dtype=float)
    width_deg = lon_span * aspect
    lon_zoom = float(np.interp(width_deg, lon_zoom_range, zoom_levels))
    lat_zoom = float(np.interp(lat_span, lon_zoom_range, zoom_levels))
    zoom = round(min(lon_zoom, lat_zoom), 2)
    zoom = max(0.5, min(zoom, 15))
    return {"center": center, "zoom": zoom}


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
    map_lats = [focus_lat]
    map_lons = [focus_lon]

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
                    go.Scattermap(
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
        map_lats.extend(map_df["lat"])
        map_lons.extend(map_df["lon"])
        _spoke_buckets(map_df, line_color=None)
        fig_map.add_trace(
            go.Scattermap(
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
            map_lats.extend(a_df["lat"])
            map_lons.extend(a_df["lon"])
            airline_summaries.append(f"{a_name}: {len(df_a):,} flights")
            _spoke_buckets(a_df, line_color=None if use_traffic_colors else color)
            fig_map.add_trace(
                go.Scattermap(
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
        go.Scattermap(
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
    map_opts = _get_map_layout_opts(geo_scope)
    map_opts.update(_map_center_zoom_from_coords(map_lats, map_lons))
    map_opts["uirevision"] = f"focus-map-{focus_airport}"
    fig_map.update_layout(
        map=map_opts,
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
            go.Scattermap(
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
                    go.Scattermap(
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

    fig_map.update_layout(
        map={**_get_map_layout_opts(geo_scope), "uirevision": "network-map"},
        height=600,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=show_legend,
    )
    st.plotly_chart(fig_map, width="stretch")


def _render_region_airport_map(
    dest_counts: "pd.Series",
    df_map: pd.DataFrame,
    geo_scope: str,
    *,
    exclude_iatas: set[str] | None = None,
    top_routes_n: int | None = None,
) -> None:
    """Render airport map centered on a region, without a hub focus airport."""
    exclude_iatas = exclude_iatas or set()
    filtered = dest_counts[~dest_counts.index.isin(exclude_iatas)]
    if top_routes_n is not None and top_routes_n > 0:
        filtered = filtered.head(top_routes_n)
    if filtered.empty:
        st.info("No airports with valid coordinates to display on map.")
        return

    map_data = build_map_points(filtered, by_country=False)
    map_df = pd.DataFrame(map_data)
    if map_df.empty:
        st.info("No airports with valid coordinates in the reference data.")
        return

    shown_iatas = set(filtered.index)
    route_df = df_map[
        df_map["origin"].isin(shown_iatas) & df_map["destination"].isin(shown_iatas)
    ]

    _arc_widths = [1.0, 2.4, 4.4, 7.0]
    _arc_colors = ["#7ecbff", "#2196f3", "#ff9800", "#e53935"]
    fig_map = go.Figure()

    if not route_df.empty:
        route_counts = (
            route_df.groupby(["origin", "destination"])
            .size()
            .sort_values(ascending=False)
        )
        if top_routes_n is not None and top_routes_n > 0:
            route_counts = route_counts.head(top_routes_n)
        q25, q50, q75 = (
            route_counts.quantile(0.25),
            route_counts.quantile(0.50),
            route_counts.quantile(0.75),
        )
        bucket_lons: list[list[float | None]] = [[] for _ in _arc_widths]
        bucket_lats: list[list[float | None]] = [[] for _ in _arc_widths]
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
        for b, (width, bcolor) in enumerate(zip(_arc_widths, _arc_colors)):
            if bucket_lons[b]:
                fig_map.add_trace(
                    go.Scattermap(
                        lon=bucket_lons[b],
                        lat=bucket_lats[b],
                        mode="lines",
                        line=dict(width=width, color=bcolor),
                        opacity=0.5,
                        hoverinfo="skip",
                        showlegend=False,
                    )
                )

    fig_map.add_trace(
        go.Scattermap(
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

    map_opts = _get_map_layout_opts(geo_scope)
    map_opts.update(_map_center_zoom_from_coords(map_df["lat"], map_df["lon"]))
    map_opts["uirevision"] = "region-airport-map"
    fig_map.update_layout(
        map=map_opts,
        height=600,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )
    st.plotly_chart(fig_map, width="stretch")


def _render_route_top_airports_tab(
    df_route: pd.DataFrame,
    airport_counts: pd.Series,
    direction: str,
    focus_airport: str | None,
    geo_scope: str,
    top_n: int,
    start_date,
    end_date,
    *,
    map_exclude_iatas: set[str] | None = None,
) -> None:
    """Render Top airports breakdown: bar chart, map, time series, and table."""
    _airport_n = min(top_n, len(airport_counts))
    _total_route = len(df_route)
    _airport_rows = []
    for iata, count in airport_counts.head(_airport_n).items():
        apt = get_airport(iata)
        share = 100 * count / _total_route if _total_route > 0 else 0
        _airport_rows.append(
            {
                "Airport": iata,
                "Name": apt.name if apt else "",
                "City": apt.city if apt else "",
                "Flights": count,
                "Share (%)": round(share, 1),
            }
        )
    _airport_df = pd.DataFrame(
        _airport_rows,
        columns=["Airport", "Name", "City", "Flights", "Share (%)"],
    )
    if _airport_df.empty:
        st.caption("No airport data for this route.")
        return

    _airport_df["Label"] = _airport_df.apply(
        lambda r: (
            f"{r['Airport']} - {r['Name']}" if r["Name"] else r["Airport"]
        ),
        axis=1,
    )
    fig_airports = px.bar(
        _airport_df,
        x="Flights",
        y="Label",
        orientation="h",
        color="Share (%)",
        color_continuous_scale="Viridis",
        range_color=[0, 100],
        labels={"Flights": "Number of flights", "Share (%)": "Share (%)"},
        text=_airport_df["Share (%)"].apply(lambda x: f"{x}%"),
        custom_data=["Flights", "Share (%)"],
    )
    fig_airports.update_traces(
        hovertemplate="%{y}<br>Flights: %{customdata[0]:,}<br>Share: %{customdata[1]}%<extra></extra>",
        textposition="outside",
    )
    fig_airports.update_layout(
        height=300 + _airport_n * 12,
        yaxis={"categoryorder": "total ascending"},
        showlegend=False,
    )
    _start_flight_count_axis_at_zero(fig_airports, "x")
    st.plotly_chart(fig_airports, width="stretch")

    _top_iatas = set(airport_counts.head(_airport_n).index)
    _map_exclude = map_exclude_iatas or set()
    _render_region_airport_map(
        airport_counts,
        df_route,
        geo_scope,
        exclude_iatas=_map_exclude,
        top_routes_n=_airport_n,
    )

    if focus_airport is None or direction == "Departures":
        _route_dest = df_route["destination"]
    elif direction == "Arrivals":
        _route_dest = df_route["origin"]
    else:
        _route_dest = pd.Series(
            np.where(
                df_route["origin"] == focus_airport,
                df_route["destination"],
                df_route["origin"],
            ),
            index=df_route.index,
        )
    _by_date_airport = (
        df_route.assign(route_dest=_route_dest)
        .groupby([df_route["date"].dt.date, "route_dest"])
        .size()
        .reset_index(name="Flights")
    )
    _by_date_airport.columns = ["Date", "route_dest", "Flights"]
    _by_date_airport = _by_date_airport[_by_date_airport["route_dest"].isin(_top_iatas)]
    _by_date_airport["Airport label"] = _by_date_airport["route_dest"].apply(
        lambda iata: (
            f"{iata} - {get_airport(iata).name}" if get_airport(iata) else iata
        )
    )
    if not _by_date_airport.empty:
        _by_date_airport = _complete_daily_series(
            _by_date_airport,
            date_col="Date",
            value_cols=["Flights"],
            start_date=start_date,
            end_date=end_date,
            group_cols=["route_dest", "Airport label"],
        )
        fig_airport_time = px.line(
            _by_date_airport,
            x="Date",
            y="Flights",
            color="Airport label",
            labels={"Flights": "Number of flights"},
        )
        fig_airport_time.update_layout(
            height=350,
            title="Flights over time by airport",
        )
        _start_flight_count_axis_at_zero(fig_airport_time, "y")
        st.plotly_chart(fig_airport_time, width="stretch")

    _render_aggrid(
        _airport_df[["Airport", "Name", "City", "Flights", "Share (%)"]]
    )
