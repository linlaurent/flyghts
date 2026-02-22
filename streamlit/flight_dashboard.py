"""
Flight Dashboard - Analyze HK flight data from flights.csv

Run with: uv run streamlit run streamlit/flight_dashboard.py
"""

from datetime import date as date_type
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from flyghts.reference import get_airline, get_airport

HKG = "HKG"
HKG_LAT = 22.3080
HKG_LON = 113.9185
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLIGHTS_CSV = PROJECT_ROOT / "flights.csv"


@st.cache_data
def load_flights() -> pd.DataFrame:
    """Load and parse flights.csv."""
    df = pd.read_csv(FLIGHTS_CSV)
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
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    cargo_filter: str | None = None,
    operating_only: bool = False,
) -> pd.DataFrame:
    """Filter by direction, date range, optionally cargo, and optionally operating-only."""
    mask = (df["date"] >= start_date) & (df["date"] <= end_date)
    if direction == "From HKG":
        mask = mask & (df["origin"] == HKG)
    elif direction == "To HKG":
        mask = mask & (df["destination"] == HKG)
    if cargo_filter and "cargo" in df.columns:
        if cargo_filter == "Passenger only":
            mask = mask & (~df["cargo"])
        elif cargo_filter == "Cargo only":
            mask = mask & df["cargo"]
    if operating_only and "operating_airline" in df.columns:
        mask = mask & (df["airline"] == df["operating_airline"])
    return df[mask]


def get_destination_column(df: pd.DataFrame, direction: str) -> pd.Series:
    """Return the series of non-HKG airport codes (destination for analysis)."""
    if direction == "From HKG":
        return df["destination"]
    if direction == "To HKG":
        return df["origin"]
    # Both: concatenate origin and destination, exclude HKG
    origins = df[df["origin"] != HKG]["origin"]
    dests = df[df["destination"] != HKG]["destination"]
    return pd.concat([origins, dests])


def main() -> None:
    st.set_page_config(
        page_title="Flight Dashboard",
        page_icon="✈️",
        layout="wide",
    )
    st.title("✈️ HK Flight Traffic Dashboard")
    st.caption("Analyze flight data to/from Hong Kong International Airport (HKG)")

    df_all = load_flights()
    min_date = df_all["date"].min().date()
    max_date = df_all["date"].max().date()
    default_date = date_type(2026, 2, 20)
    start_end_default = default_date if min_date <= default_date <= max_date else min_date

    # Sidebar filters
    with st.sidebar:
        st.header("Filters")
        direction = st.radio(
            "Direction",
            options=["From HKG", "To HKG", "Both"],
            index=2,
            help="From HKG = departures, To HKG = arrivals, Both = all flights",
        )
        start_date = st.date_input(
            "Start date",
            value=start_end_default,
            min_value=min_date,
            max_value=max_date,
        )
        end_date = st.date_input(
            "End date",
            value=start_end_default,
            min_value=min_date,
            max_value=max_date,
        )
        top_n = st.slider("Top N for rankings", min_value=5, max_value=50, value=20)

        has_cargo = "cargo" in df_all.columns
        if has_cargo:
            cargo_filter = st.radio(
                "Flight type",
                options=["All", "Passenger only", "Cargo only"],
                index=1,
                help="Filter by passenger vs cargo flights (requires cargo column in data)",
            )
        else:
            cargo_filter = None
            st.caption("No cargo column in data. Re-dump with --cargo to enable.")

        has_operating = "operating_airline" in df_all.columns
        if has_operating:
            operating_only = st.checkbox(
                "Operating carrier only",
                value=True,
                help="Exclude code-share duplicates; show one row per physical flight",
            )
        else:
            operating_only = False
            st.caption("No operating carrier columns. Re-dump to enable.")

    if start_date > end_date:
        st.error("Start date must be before or equal to end date.")
        return

    df = apply_filters(
        df_all,
        direction,
        pd.Timestamp(start_date),
        pd.Timestamp(end_date),
        cargo_filter=cargo_filter if has_cargo else None,
        operating_only=operating_only if has_operating else False,
    )
    total_flights = len(df)

    st.metric("Total flights (filtered)", f"{total_flights:,}")

    # --- Filtered data table ---
    with st.expander("View filtered data", expanded=False):
        # Column filters
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            origins = sorted(df["origin"].dropna().unique().tolist())
            sel_origin = st.multiselect(
                "Origin",
                options=origins,
                default=[],
                help="Leave empty to show all",
            )
        with col2:
            destinations = sorted(df["destination"].dropna().unique().tolist())
            sel_dest = st.multiselect(
                "Destination",
                options=destinations,
                default=[],
                help="Leave empty to show all",
            )
        with col3:
            airline_col_sel = "operating_airline" if (operating_only and has_operating) else "airline"
            airlines = sorted(df[airline_col_sel].dropna().unique().tolist())
            sel_airline = st.multiselect(
                "Airline",
                options=airlines,
                default=[],
                help="Leave empty to show all",
            )
        with col4:
            search = st.text_input(
                "Search",
                placeholder="Search in flight_no, status...",
                help="Case-insensitive search across flight_no and status",
            )

        df_display = df.copy()
        if sel_origin:
            df_display = df_display[df_display["origin"].isin(sel_origin)]
        if sel_dest:
            df_display = df_display[df_display["destination"].isin(sel_dest)]
        if sel_airline:
            col_for_filter = "operating_airline" if (operating_only and has_operating) else "airline"
            df_display = df_display[df_display[col_for_filter].isin(sel_airline)]
        if search:
            search_lower = search.strip().lower()
            mask = (
                df_display["flight_no"].astype(str).str.lower().str.contains(search_lower, na=False)
                | df_display["status"].astype(str).str.lower().str.contains(search_lower, na=False)
            )
            df_display = df_display[mask]

        st.caption(f"Showing {len(df_display):,} of {len(df):,} rows")
        col_config = {
            "date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "scheduled_time": st.column_config.DatetimeColumn("Scheduled", format="YYYY-MM-DD HH:mm"),
            **({"cargo": st.column_config.CheckboxColumn("Cargo")} if "cargo" in df.columns else {}),
            **({"operating_airline": st.column_config.TextColumn("Operating")} if "operating_airline" in df.columns else {}),
        }
        st.dataframe(df_display, width="stretch", column_config=col_config)

    # --- Top Companies ---
    st.header("Top airlines by flight count")
    airline_col = "operating_airline" if (operating_only and has_operating) else "airline"
    airline_counts = df[airline_col].value_counts()
    top_airlines = airline_counts.head(top_n)

    airline_rows = []
    for icao, count in top_airlines.items():
        info = get_airline(icao)
        name = info.name if info else icao
        country = info.country if info else ""
        airline_rows.append(
            {"Airline": name, "ICAO": icao, "Country": country, "Flights": count}
        )
    airline_df = pd.DataFrame(
        airline_rows,
        columns=["Airline", "ICAO", "Country", "Flights"],
    )

    fig_airlines = px.bar(
        airline_df,
        x="Flights",
        y="Airline",
        orientation="h",
        color="Flights",
        color_continuous_scale="Blues",
        labels={"Flights": "Number of flights"},
    )
    fig_airlines.update_layout(
        height=400 + top_n * 12,
        yaxis={"categoryorder": "total ascending"},
        showlegend=False,
    )
    st.plotly_chart(fig_airlines, width="stretch")
    with st.expander("View table"):
        st.dataframe(airline_df, width="stretch")

    # --- Top Destinations ---
    st.header("Top destinations")
    dest_codes = get_destination_column(df, direction)
    dest_counts = dest_codes.value_counts()

    tab_airport, tab_city, tab_country = st.tabs([
        "By airport (IATA)",
        "By city",
        "By country",
    ])

    with tab_airport:
        airport_rows = []
        for iata, count in dest_counts.head(top_n).items():
            info = get_airport(iata)
            airport_rows.append({
                "Airport": iata,
                "Name": info.name if info else "",
                "City": info.city if info else "",
                "Country": info.country if info else "",
                "Flights": count,
            })
        airport_df = pd.DataFrame(
            airport_rows,
            columns=["Airport", "Name", "City", "Country", "Flights"],
        )
        display_df = airport_df.copy()
        display_df["Label"] = display_df.apply(
            lambda r: f"{r['Airport']} - {r['Name']}" if r["Name"] else r["Airport"],
            axis=1,
        )
        fig_apt = px.bar(
            display_df,
            x="Flights",
            y="Label",
            orientation="h",
            color="Flights",
            color_continuous_scale="Greens",
        )
        fig_apt.update_layout(
            height=400 + min(top_n, len(display_df)) * 12,
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
        )
        st.plotly_chart(fig_apt, width="stretch")
        st.dataframe(airport_df[["Airport", "Name", "City", "Country", "Flights"]])

    with tab_city:
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
        fig_city = px.bar(
            city_df,
            x="Flights",
            y="City",
            orientation="h",
            color="Flights",
            color_continuous_scale="Oranges",
        )
        fig_city.update_layout(
            height=400 + min(top_n, len(city_df)) * 12,
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
        )
        st.plotly_chart(fig_city, width="stretch")
        st.dataframe(city_df)

    with tab_country:
        country_counts: dict[str, int] = {}
        for iata, count in dest_counts.items():
            info = get_airport(iata)
            country = info.country if info and info.country else iata
            country_counts[country] = country_counts.get(country, 0) + count
        country_sorted = sorted(country_counts.items(), key=lambda x: -x[1])[:top_n]
        country_df = pd.DataFrame(
            [{"Country": c, "Flights": n} for c, n in country_sorted],
            columns=["Country", "Flights"],
        )
        fig_country = px.bar(
            country_df,
            x="Flights",
            y="Country",
            orientation="h",
            color="Flights",
            color_continuous_scale="Purples",
        )
        fig_country.update_layout(
            height=400 + min(top_n, len(country_df)) * 12,
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
        )
        st.plotly_chart(fig_country, width="stretch")
        st.dataframe(country_df)

    # --- Interactive Map ---
    st.header("Interactive map: flight flow by destination")

    map_point_by = st.radio(
        "Map points by",
        options=["City (airport)", "Country"],
        index=0,
        horizontal=True,
        help="Show each destination as a precise city/airport, or aggregate by country.",
    )
    map_by_country = map_point_by == "Country"

    # Map filter: operating airline (optional) – use same column as top airlines for consistency
    map_airline_col = "operating_airline" if (operating_only and has_operating) else "airline"
    map_airlines = sorted(df[map_airline_col].dropna().unique().tolist())
    map_airline_options = ["All"]
    map_display_to_code: dict[str, str] = {}
    for code in map_airlines:
        display = f"{code} - {info.name}" if (info := get_airline(code)) and info.name else code
        map_airline_options.append(display)
        map_display_to_code[display] = code
    sel_map_airline = st.selectbox(
        "Filter by airline",
        options=map_airline_options,
        index=0,
        help="Only affects the map.",
    )
    df_map = df
    if sel_map_airline != "All":
        df_map = df[df[map_airline_col] == map_display_to_code[sel_map_airline]]
    map_dest_counts = get_destination_column(df_map, direction).value_counts()

    map_data = []
    for iata, count in map_dest_counts.items():
        info = get_airport(iata)
        if info and (info.latitude != 0 or info.longitude != 0):
            map_data.append({
                "iata": iata,
                "lat": info.latitude,
                "lon": info.longitude,
                "count": count,
                "label": f"{iata} ({info.city or '?'}, {info.country or '?'}): {count}",
            })
    map_df = pd.DataFrame(map_data)

    if map_df.empty:
        st.info("No destination airports with valid coordinates in the reference data.")
    else:
        if sel_map_airline != "All":
            st.caption(f"Map shows {len(df_map):,} flights from {sel_map_airline}")
        fig_map = go.Figure()

        # Flow lines from HKG to each destination (line width ∝ flight count)
        count_max = map_df["count"].max()
        for _, row in map_df.iterrows():
            # Scale width from 0.8 to 8 based on relative importance
            rel = row["count"] / count_max if count_max > 0 else 1
            width = 0.8 + 7.2 * rel
            fig_map.add_trace(
                go.Scattergeo(
                    lon=[HKG_LON, row["lon"]],
                    lat=[HKG_LAT, row["lat"]],
                    mode="lines",
                    line=dict(width=width, color="rgba(100,150,200,0.5)"),
                    hoverinfo="skip",
                )
            )

        # Destination markers (size = flight count)
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
            )
        )

        # HKG marker
        fig_map.add_trace(
            go.Scattergeo(
                lon=[HKG_LON],
                lat=[HKG_LAT],
                text=["HKG (Hong Kong)"],
                mode="markers+text",
                marker=dict(size=15, color="red", symbol="star"),
                textposition="top center",
                hoverinfo="text",
            )
        )

        fig_map.update_geos(
            scope="world",
            projection_type="natural earth",
            showland=True,
            coastlinewidth=0.5,
            landcolor="rgb(243,243,243)",
        )
        fig_map.update_layout(
            height=600,
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False,
        )
        st.plotly_chart(fig_map, width="stretch")

    # --- Airline deep dive ---
    st.header("Airline deep dive")
    dive_airlines = sorted(df[airline_col].dropna().unique().tolist())
    dive_airline_options: list[str] = []
    dive_display_to_code: dict[str, str] = {}
    for code in dive_airlines:
        display = f"{code} - {info.name}" if (info := get_airline(code)) and info.name else code
        dive_airline_options.append(display)
        dive_display_to_code[display] = code

    if not dive_airline_options:
        st.info("No airlines in the filtered data.")
    else:
        default_dive_idx = 0
        for i, opt in enumerate(dive_airline_options):
            if opt.startswith("CPA -") or dive_display_to_code.get(opt) == "CPA":
                default_dive_idx = i
                break

        sel_dive_airline = st.selectbox(
            "Select airline",
            options=dive_airline_options,
            index=min(default_dive_idx, len(dive_airline_options) - 1),
            help="Explore statistics for a single airline.",
        )
        dive_icao = dive_display_to_code.get(sel_dive_airline, "") if sel_dive_airline else ""
        df_airline = df[df[airline_col] == dive_icao] if dive_icao else pd.DataFrame()

        if df_airline.empty:
            st.info("No flights for this airline in the selected filters.")
        else:
            dive_name = get_airline(dive_icao).name if get_airline(dive_icao) else dive_icao
            st.subheader(f"{dive_name}")

            n_airline = len(df_airline)
            pct = 100 * n_airline / total_flights if total_flights > 0 else 0
            m1, m2 = st.columns(2)
            with m1:
                st.metric("Total flights", f"{n_airline:,}")
            with m2:
                st.metric("Share of traffic", f"{pct:.1f}%")

            dest_codes_airline = get_destination_column(df_airline, direction)
            dest_counts_airline = dest_codes_airline.value_counts()
            if direction == "From HKG":
                route_dest_airline = df_airline["destination"]
            elif direction == "To HKG":
                route_dest_airline = df_airline["origin"]
            else:
                route_dest_airline = pd.Series(
                    np.where(df_airline["origin"] == HKG, df_airline["destination"], df_airline["origin"]),
                    index=df_airline.index,
                )

            tab_routes, tab_time, tab_hour, tab_cargo = st.tabs([
                "Top routes",
                "Flights over time",
                "Flights by hour",
                "Cargo vs passenger",
            ])

            with tab_routes:
                route_n = min(top_n, len(dest_counts_airline))
                # Denominator: match operating_only—physical flights when True, all records when False
                total_dest_counts = get_destination_column(df, direction).value_counts()
                route_rows = []
                for iata, count in dest_counts_airline.head(route_n).items():
                    info = get_airport(iata)
                    total_to_dest = total_dest_counts.get(iata, 0)
                    share = 100 * count / total_to_dest if total_to_dest > 0 else 0
                    route_rows.append({
                        "Airport": iata,
                        "Name": info.name if info else "",
                        "City": info.city if info else "",
                        "Country": info.country if info else "",
                        "Flights": count,
                        "Total": total_to_dest,
                        "Share (%)": round(share, 1),
                    })
                route_df = pd.DataFrame(
                    route_rows,
                    columns=["Airport", "Name", "City", "Country", "Flights", "Total", "Share (%)"],
                )
                if not route_df.empty:
                    route_df["Label"] = route_df.apply(
                        lambda r: f"{r['Airport']} - {r['Name']}" if r["Name"] else r["Airport"],
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
                        labels={"Flights": "Number of flights", "Share (%)": "Share (%)"},
                        text=route_df["Share (%)"].apply(lambda x: f"{x}%"),
                        custom_data=["Flights", "Total", "Share (%)"],
                    )
                    fig_route.update_traces(
                        hovertemplate="%{y}<br>Flights: %{customdata[0]:,}<br>Total: %{customdata[1]:,}<br>Share: %{customdata[2]}%<extra></extra>",
                    )
                    fig_route.update_layout(
                        height=300 + route_n * 12,
                        yaxis={"categoryorder": "total ascending"},
                        showlegend=False,
                    )
                    fig_route.update_traces(textposition="outside")
                    st.plotly_chart(fig_route, width="stretch")

                    # Share % over time for top N routes
                    top_dests = set(dest_counts_airline.head(route_n).index)
                    by_date_dest = (
                        df_airline.assign(route_dest=route_dest_airline)
                        .groupby([df_airline["date"].dt.date, "route_dest"])
                        .size()
                        .reset_index(name="Flights")
                    )
                    by_date_dest.columns = ["Date", "route_dest", "Flights"]
                    by_date_dest = by_date_dest[by_date_dest["route_dest"].isin(top_dests)]
                    if direction == "From HKG":
                        dest_col_df = df["destination"]
                    elif direction == "To HKG":
                        dest_col_df = df["origin"]
                    else:
                        dest_col_df = pd.Series(
                            np.where(df["origin"] == HKG, df["destination"], df["origin"]),
                            index=df.index,
                        )
                    total_by_date_dest = (
                        df.assign(route_dest=dest_col_df)
                        .groupby([df["date"].dt.date, "route_dest"])
                        .size()
                        .reset_index(name="Total")
                    )
                    total_by_date_dest.columns = ["Date", "route_dest", "Total"]
                    by_date_dest = by_date_dest.merge(
                        total_by_date_dest,
                        on=["Date", "route_dest"],
                        how="left",
                    )
                    by_date_dest["Share (%)"] = (
                        100 * by_date_dest["Flights"] / by_date_dest["Total"]
                    ).round(1)
                    by_date_dest["Route"] = by_date_dest["route_dest"].apply(
                        lambda iata: get_airport(iata).name if get_airport(iata) else iata
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
                        st.plotly_chart(fig_route_share_time, width="stretch")

                    # Flights per route normalized by airline's daily flights
                    airline_flights_per_date = (
                        df_airline.groupby(df_airline["date"].dt.date).size().rename("AirlineTotal")
                    )
                    by_date_dest_norm = (
                        df_airline.assign(route_dest=route_dest_airline)
                        .groupby([df_airline["date"].dt.date, "route_dest"])
                        .size()
                        .reset_index(name="Flights")
                    )
                    by_date_dest_norm.columns = ["Date", "route_dest", "Flights"]
                    by_date_dest_norm = by_date_dest_norm[by_date_dest_norm["route_dest"].isin(top_dests)]
                    by_date_dest_norm = by_date_dest_norm.merge(
                        airline_flights_per_date,
                        left_on="Date",
                        right_index=True,
                        how="left",
                    )
                    by_date_dest_norm["Norm (%)"] = (
                        100 * by_date_dest_norm["Flights"] / by_date_dest_norm["AirlineTotal"]
                    ).round(1)
                    by_date_dest_norm["Route"] = by_date_dest_norm["route_dest"].apply(
                        lambda iata: get_airport(iata).name if get_airport(iata) else iata
                    )
                    if not by_date_dest_norm.empty:
                        fig_route_norm = px.line(
                            by_date_dest_norm,
                            x="Date",
                            y="Norm (%)",
                            color="Route",
                            labels={"Norm (%)": "Share of airline flights (%)"},
                            custom_data=["Flights", "AirlineTotal", "Route"],
                        )
                        fig_route_norm.update_traces(
                            hovertemplate="%{customdata[2]}<br>%{x}<br>Flights: %{customdata[0]:,}<br>Airline total (denom): %{customdata[1]:,}<br>Norm: %{y}%<extra></extra>",
                        )
                        fig_route_norm.update_layout(
                            height=350,
                            title="Share of airline flights (%) over time by route",
                            yaxis=dict(title="Share of airline flights (%)"),
                        )
                        st.plotly_chart(fig_route_norm, width="stretch")

                st.dataframe(route_df[["Airport", "Name", "City", "Country", "Flights", "Share (%)"]] if not route_df.empty else pd.DataFrame())

            with tab_time:
                by_date = df_airline.groupby(df_airline["date"].dt.date).size().reset_index(name="Flights")
                by_date.columns = ["Date", "Flights"]
                if not by_date.empty:
                    total_by_date = df.groupby(df["date"].dt.date).size().reset_index(name="Total")
                    total_by_date.columns = ["Date", "Total"]
                    share_df = by_date.merge(total_by_date, on="Date", how="left")
                    share_df["Share"] = (
                        100 * share_df["Flights"] / share_df["Total"]
                    ).fillna(0)

                    fig_time = go.Figure()
                    fig_time.add_trace(
                        go.Scatter(
                            x=share_df["Date"],
                            y=share_df["Flights"],
                            name="Flights",
                            line=dict(color="#1f77b4"),
                        )
                    )
                    fig_time.add_trace(
                        go.Scatter(
                            x=share_df["Date"],
                            y=share_df["Share"],
                            name="Share of traffic (%)",
                            yaxis="y2",
                            line=dict(color="#ff7f0e"),
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
                    st.plotly_chart(fig_time, width="stretch")

                    # Flights over time per route (top N)
                    top_dests_time = set(dest_counts_airline.head(top_n).index)
                    by_date_dest_time = (
                        df_airline.assign(route_dest=route_dest_airline)
                        .groupby([df_airline["date"].dt.date, "route_dest"])
                        .size()
                        .reset_index(name="Flights")
                    )
                    by_date_dest_time.columns = ["Date", "route_dest", "Flights"]
                    by_date_dest_time = by_date_dest_time[
                        by_date_dest_time["route_dest"].isin(top_dests_time)
                    ]
                    by_date_dest_time = by_date_dest_time.merge(
                        total_by_date_dest[["Date", "route_dest", "Total"]],
                        on=["Date", "route_dest"],
                        how="left",
                    )
                    by_date_dest_time["Route"] = by_date_dest_time["route_dest"].apply(
                        lambda iata: get_airport(iata).name if get_airport(iata) else iata
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
                        st.plotly_chart(fig_route_count_time, width="stretch")
                else:
                    st.caption("No date data.")

            with tab_hour:
                if "scheduled_time" in df_airline.columns:
                    df_airline_hour = df_airline.dropna(subset=["scheduled_time"])
                    df_airline_hour = df_airline_hour.copy()
                    df_airline_hour["hour"] = pd.to_datetime(df_airline_hour["scheduled_time"], errors="coerce").dt.hour
                    df_airline_hour = df_airline_hour.dropna(subset=["hour"])
                    by_hour = df_airline_hour.groupby("hour").size().reset_index(name="Flights")
                    if not by_hour.empty:
                        fig_hour = px.bar(
                            by_hour,
                            x="hour",
                            y="Flights",
                            labels={"hour": "Hour of day", "Flights": "Number of flights"},
                        )
                        fig_hour.update_layout(height=350)
                        st.plotly_chart(fig_hour, width="stretch")
                    else:
                        st.caption("No scheduled time data for this airline.")
                else:
                    st.caption("No scheduled_time column in data.")

            with tab_cargo:
                if "cargo" in df_airline.columns:
                    cargo_by_date = df_airline.groupby(
                        [df_airline["date"].dt.date, "cargo"]
                    ).size().reset_index(name="Flights")
                    cargo_by_date["Type"] = cargo_by_date["cargo"].map(
                        {True: "Cargo", False: "Passenger"}
                    )
                    if not cargo_by_date.empty:
                        fig_cargo = px.line(
                            cargo_by_date,
                            x="date",
                            y="Flights",
                            color="Type",
                            labels={"date": "Date", "Flights": "Number of flights"},
                            custom_data=["Type"],
                        )
                        fig_cargo.update_traces(
                            hovertemplate="%{customdata[0]}<br>%{x}<br>Flights: %{y:,}<extra></extra>",
                        )
                        fig_cargo.update_layout(height=350)
                        st.plotly_chart(fig_cargo, width="stretch")
                    cargo_passenger = (df_airline["cargo"] == False).sum()
                    cargo_cargo = (df_airline["cargo"] == True).sum()
                    cargo_df = pd.DataFrame([
                        {"Type": "Passenger", "Flights": cargo_passenger},
                        {"Type": "Cargo", "Flights": cargo_cargo},
                    ])
                    st.dataframe(cargo_df)
                else:
                    st.caption("No cargo column in data.")

    # --- Route deep dive ---
    st.header("Route deep dive")
    # Group bidirectional routes: HKG-TPE and TPE-HKG become one route with summed counts
    route_series = df["origin"] + "-" + df["destination"]
    route_pairs = route_series.apply(lambda s: "-".join(sorted(s.split("-", 1))) if "-" in s else s)
    route_counts = route_pairs.value_counts()
    route_options_raw = route_counts.head(min(30, len(route_counts)))
    route_display_options: list[str] = []
    route_str_to_airports: dict[str, tuple[str, str]] = {}
    for route_str, count in route_options_raw.items():
        parts = route_str.split("-", 1)
        if len(parts) == 2:
            a, b = parts[0], parts[1]
            other = b if a == HKG else a
            info = get_airport(other)
            name = info.name if info and info.name else other
            label = f"{other} - {name} - {count:,} flights"
            route_display_options.append(label)
            route_str_to_airports[label] = (a, b)

    if not route_display_options:
        st.info("No routes in the filtered data.")
    else:
        sel_route_display = st.selectbox(
            "Select route",
            options=route_display_options,
            index=0,
            help="Explore statistics for a route (both directions grouped).",
        )
        airport_a, airport_b = route_str_to_airports.get(sel_route_display, ("", ""))
        mask_both = (
            ((df["origin"] == airport_a) & (df["destination"] == airport_b))
            | ((df["origin"] == airport_b) & (df["destination"] == airport_a))
        )
        df_route = df[mask_both]

        if df_route.empty:
            st.info("No flights for this route in the selected filters.")
        else:
            other = airport_b if airport_a == HKG else airport_a
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

            tab_route_airlines, tab_route_time, tab_route_hour, tab_route_cargo = st.tabs([
                "Top airlines",
                "Flights over time",
                "Flights by hour",
                "Cargo vs passenger",
            ])

            with tab_route_airlines:
                airline_counts_route = df_route[airline_col].value_counts()
                total_on_route = len(df_route)
                airline_rows = []
                for icao, count in airline_counts_route.head(top_n).items():
                    info = get_airline(icao)
                    name = info.name if info else icao
                    share = 100 * count / total_on_route if total_on_route > 0 else 0
                    airline_rows.append({
                        "Airline": name,
                        "ICAO": icao,
                        "Flights": count,
                        "Share (%)": round(share, 1),
                    })
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
                        labels={"Flights": "Number of flights", "Share (%)": "Share (%)"},
                        text=airline_route_df["Share (%)"].apply(lambda x: f"{x}%"),
                    )
                    fig_route_airlines.update_layout(
                        height=300 + min(top_n, len(airline_route_df)) * 12,
                        yaxis={"categoryorder": "total ascending"},
                        showlegend=False,
                    )
                    fig_route_airlines.update_traces(textposition="outside")
                    st.plotly_chart(fig_route_airlines, width="stretch")

                    # Share per day by airline (top N only)
                    top_airlines_route = set(airline_counts_route.head(top_n).index)
                    by_date_airline = (
                        df_route.groupby([df_route["date"].dt.date, airline_col])
                        .size()
                        .reset_index(name="Flights")
                    )
                    by_date_airline.columns = ["Date", "ICAO", "Flights"]
                    total_per_date = df_route.groupby(df_route["date"].dt.date).size()
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

                st.dataframe(airline_route_df[["Airline", "ICAO", "Flights", "Share (%)"]] if not airline_route_df.empty else pd.DataFrame())

            with tab_route_time:
                by_date_route = df_route.groupby(df_route["date"].dt.date).size().reset_index(name="Flights")
                by_date_route.columns = ["Date", "Flights"]
                if not by_date_route.empty:
                    total_by_date = df.groupby(df["date"].dt.date).size().reset_index(name="Total")
                    total_by_date.columns = ["Date", "Total"]
                    share_route_df = by_date_route.merge(total_by_date, on="Date", how="left")
                    share_route_df["Share"] = (
                        100 * share_route_df["Flights"] / share_route_df["Total"]
                    ).fillna(0)

                    fig_route_time = go.Figure()
                    fig_route_time.add_trace(
                        go.Scatter(
                            x=share_route_df["Date"],
                            y=share_route_df["Flights"],
                            name="Flights",
                            line=dict(color="#1f77b4"),
                        )
                    )
                    fig_route_time.add_trace(
                        go.Scatter(
                            x=share_route_df["Date"],
                            y=share_route_df["Share"],
                            name="Share of traffic (%)",
                            yaxis="y2",
                            line=dict(color="#ff7f0e"),
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
                    st.plotly_chart(fig_route_time, width="stretch")

                    # Flights over time per airline (top N only)
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
                    total_per_date_route = df_route.groupby(df_route["date"].dt.date).size().rename("Total")
                    by_date_airline_time = by_date_airline_time.merge(
                        total_per_date_route,
                        left_on="Date",
                        right_index=True,
                        how="left",
                    )
                    by_date_airline_time["Airline"] = by_date_airline_time["ICAO"].apply(
                        lambda c: get_airline(c).name if get_airline(c) else c
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
                        st.plotly_chart(fig_count_day, width="stretch")
                else:
                    st.caption("No date data.")

            with tab_route_hour:
                if "scheduled_time" in df_route.columns:
                    df_route_hour = df_route.dropna(subset=["scheduled_time"])
                    df_route_hour = df_route_hour.copy()
                    df_route_hour["hour"] = pd.to_datetime(df_route_hour["scheduled_time"], errors="coerce").dt.hour
                    df_route_hour = df_route_hour.dropna(subset=["hour"])
                    by_hour_route = df_route_hour.groupby("hour").size().reset_index(name="Flights")
                    if not by_hour_route.empty:
                        fig_route_hour = px.bar(
                            by_hour_route,
                            x="hour",
                            y="Flights",
                            labels={"hour": "Hour of day", "Flights": "Number of flights"},
                        )
                        fig_route_hour.update_layout(height=350)
                        st.plotly_chart(fig_route_hour, width="stretch")
                    else:
                        st.caption("No scheduled time data for this route.")
                else:
                    st.caption("No scheduled_time column in data.")

            with tab_route_cargo:
                if "cargo" in df_route.columns:
                    cargo_by_date_route = df_route.groupby(
                        [df_route["date"].dt.date, "cargo"]
                    ).size().reset_index(name="Flights")
                    cargo_by_date_route["Type"] = cargo_by_date_route["cargo"].map(
                        {True: "Cargo", False: "Passenger"}
                    )
                    if not cargo_by_date_route.empty:
                        fig_route_cargo = px.line(
                            cargo_by_date_route,
                            x="date",
                            y="Flights",
                            color="Type",
                            labels={"date": "Date", "Flights": "Number of flights"},
                            custom_data=["Type"],
                        )
                        fig_route_cargo.update_traces(
                            hovertemplate="%{customdata[0]}<br>%{x}<br>Flights: %{y:,}<extra></extra>",
                        )
                        fig_route_cargo.update_layout(height=350)
                        st.plotly_chart(fig_route_cargo, width="stretch")
                    cargo_passenger_r = (df_route["cargo"] == False).sum()
                    cargo_cargo_r = (df_route["cargo"] == True).sum()
                    cargo_route_df = pd.DataFrame([
                        {"Type": "Passenger", "Flights": cargo_passenger_r},
                        {"Type": "Cargo", "Flights": cargo_cargo_r},
                    ])
                    st.dataframe(cargo_route_df)
                else:
                    st.caption("No cargo column in data.")


if __name__ == "__main__":
    main()
