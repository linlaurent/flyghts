"""
Flight Dashboard - Analyze HK flight data from flights.csv

Run with: uv run streamlit run streamlit/flight_dashboard.py
"""

from pathlib import Path

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
    return df


def apply_filters(
    df: pd.DataFrame,
    direction: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    """Filter by direction and date range."""
    mask = (df["date"] >= start_date) & (df["date"] <= end_date)
    if direction == "From HKG":
        mask = mask & (df["origin"] == HKG)
    elif direction == "To HKG":
        mask = mask & (df["destination"] == HKG)
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

    # Sidebar filters
    with st.sidebar:
        st.header("Filters")
        direction = st.radio(
            "Direction",
            options=["From HKG", "To HKG", "Both"],
            index=0,
            help="From HKG = departures, To HKG = arrivals, Both = all flights",
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
        top_n = st.slider("Top N for rankings", min_value=5, max_value=50, value=20)

    if start_date > end_date:
        st.error("Start date must be before or equal to end date.")
        return

    df = apply_filters(
        df_all,
        direction,
        pd.Timestamp(start_date),
        pd.Timestamp(end_date),
    )
    total_flights = len(df)

    st.metric("Total flights (filtered)", f"{total_flights:,}")

    # --- Top Companies ---
    st.header("Top airlines by flight count")
    airline_counts = df["airline"].value_counts()
    top_airlines = airline_counts.head(top_n)

    airline_rows = []
    for icao, count in top_airlines.items():
        info = get_airline(icao)
        name = info.name if info else icao
        country = info.country if info else ""
        airline_rows.append(
            {"Airline": name, "ICAO": icao, "Country": country, "Flights": count}
        )
    airline_df = pd.DataFrame(airline_rows)

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
    st.plotly_chart(fig_airlines, use_container_width=True)
    with st.expander("View table"):
        st.dataframe(airline_df, use_container_width=True)

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
        airport_df = pd.DataFrame(airport_rows)
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
        st.plotly_chart(fig_apt, use_container_width=True)
        st.dataframe(airport_df[["Airport", "Name", "City", "Country", "Flights"]])

    with tab_city:
        city_counts: dict[str, int] = {}
        for iata, count in dest_counts.items():
            info = get_airport(iata)
            city = info.city if info and info.city else iata
            city_counts[city] = city_counts.get(city, 0) + count
        city_sorted = sorted(city_counts.items(), key=lambda x: -x[1])[:top_n]
        city_df = pd.DataFrame([
            {"City": c, "Flights": n} for c, n in city_sorted
        ])
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
        st.plotly_chart(fig_city, use_container_width=True)
        st.dataframe(city_df)

    with tab_country:
        country_counts: dict[str, int] = {}
        for iata, count in dest_counts.items():
            info = get_airport(iata)
            country = info.country if info and info.country else iata
            country_counts[country] = country_counts.get(country, 0) + count
        country_sorted = sorted(country_counts.items(), key=lambda x: -x[1])[:top_n]
        country_df = pd.DataFrame([
            {"Country": c, "Flights": n} for c, n in country_sorted
        ])
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
        st.plotly_chart(fig_country, use_container_width=True)
        st.dataframe(country_df)

    # --- Interactive Map ---
    st.header("Interactive map: flight flow by destination")
    map_data = []
    for iata, count in dest_counts.items():
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
        fig_map = go.Figure()

        # Flow lines from HKG to each destination
        lons = []
        lats = []
        for _, row in map_df.iterrows():
            lons.extend([HKG_LON, row["lon"], None])
            lats.extend([HKG_LAT, row["lat"], None])

        fig_map.add_trace(
            go.Scattergeo(
                lon=lons,
                lat=lats,
                mode="lines",
                line=dict(width=1, color="rgba(100,150,200,0.4)"),
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
        st.plotly_chart(fig_map, use_container_width=True)


if __name__ == "__main__":
    main()
