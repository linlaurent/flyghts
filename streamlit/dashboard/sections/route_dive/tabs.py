"""Route deep dive tab bodies."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from flyghts.reference import get_airline, get_airport

from ...charts import _complete_daily_series, _start_flight_count_axis_at_zero
from ...components import _render_aggrid
from ...context import DashboardContext
from ...formatting import (
    ALLIANCE_ORDER,
    RouteCityKey,
    _airport_city_key,
    _alliance_label,
    _city_key_display,
    _city_key_label,
    _city_pair_airport_counts,
    _multi_airport_city_keys_for_iatas,
    _route_label,
    with_alliance_column,
)
from ...maps import (
    _render_flight_map,
    _render_region_airport_map,
    _render_route_top_airports_tab,
)
from ...tab_charts import (
    render_cargo_tab,
    render_primary_flights_over_time,
    render_scheduled_hour,
    render_secondary_grouped_over_time,
    render_weekday_average,
)


def render_route_tabs(
    ctx: DashboardContext,
    *,
    df_route: pd.DataFrame,
    route_by_country: bool,
    route_by_province: bool,
    route_by_city: bool,
    sel_region: str,
    city_a: RouteCityKey | None,
    city_b: RouteCityKey | None,
    airport_a: str,
    airport_b: str,
    _route_region_airports: dict[str, set[str]],
    _route_region_country: dict[str, str],
    _route_city_iatas: dict[RouteCityKey, set[str]],
) -> None:
    _selected_multi_airport_city_keys: list[RouteCityKey] = []
    _airport_compare_city_keys: list[RouteCityKey] = []
    _airport_compare_province_iatas: set[str] = set()
    if route_by_country:
        route_label = sel_region
        _airport_compare_city_keys = _multi_airport_city_keys_for_iatas(
            _route_region_airports.get(sel_region, set())
        )
    elif route_by_province:
        country = _route_region_country.get(sel_region, "")
        route_label = f"{sel_region}, {country}" if country else sel_region
        _airport_compare_province_iatas = _route_region_airports.get(sel_region, set())
    elif route_by_city:
        if ctx.global_mode:
            route_label = f"{_city_key_label(city_a)} ↔ {_city_key_label(city_b)}"
        else:
            focus_city_key = (
                _airport_city_key(ctx.focus_airport) if ctx.focus_airport else None
            )
            if focus_city_key and (
                city_a == focus_city_key or city_b == focus_city_key
            ):
                other_city = city_b if city_a == focus_city_key else city_a
                route_label = _city_key_label(other_city)
            else:
                route_label = f"{_city_key_label(city_a)} ↔ {_city_key_label(city_b)}"
        _selected_multi_airport_city_keys = [
            city_key
            for city_key in dict.fromkeys([city_a, city_b])
            if len(_route_city_iatas.get(city_key, set())) >= 2
        ]
        _airport_compare_city_keys = _selected_multi_airport_city_keys
    elif ctx.global_mode:
        a_info = get_airport(airport_a)
        b_info = get_airport(airport_b)
        a_city = a_info.city if a_info and a_info.city else airport_a
        b_city = b_info.city if b_info and b_info.city else airport_b
        route_label = f"{airport_a} ({a_city}) ↔ {airport_b} ({b_city})"
    else:
        other = airport_b if airport_a == ctx.focus_airport else airport_a
        other_info = get_airport(other)
        name = other_info.name if other_info and other_info.name else other
        route_label = f"{other} - {name}"
    st.subheader(route_label)

    n_route = len(df_route)
    pct_route = 100 * n_route / ctx.total_flights if ctx.total_flights > 0 else 0
    m1, m2 = st.columns(2)
    with m1:
        st.metric("Total flights on route", f"{n_route:,}")
    with m2:
        st.metric("Share of traffic", f"{pct_route:.1f}%")

    _show_airport_compare = bool(_airport_compare_city_keys) or (
        route_by_province and len(_airport_compare_province_iatas) >= 2
    )

    _route_tab_names: list[str] = []
    if route_by_country or route_by_province or route_by_city:
        _route_tab_names.append("Top airports")
    if _show_airport_compare:
        _route_tab_names.append("Airport comparison")
    _route_tab_names += [
        "Top airlines",
        "Flights over time",
        "Flights by hour",
        "Flights by weekday",
    ]
    if not ctx.is_us:
        _route_tab_names.append("Cargo vs passenger")
    _route_tabs = st.tabs(_route_tab_names)
    _idx = 0
    if route_by_country or route_by_province or route_by_city:
        tab_route_top_airports = _route_tabs[_idx]
        _idx += 1
    else:
        tab_route_top_airports = None
    if _show_airport_compare:
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
    tab_route_cargo = _route_tabs[_idx] if not ctx.is_us else None

    if tab_route_top_airports is not None:
        with tab_route_top_airports:
            if route_by_city:
                _top_airport_counts = _city_pair_airport_counts(
                    df_route, city_a, city_b
                )
            else:
                _top_airport_counts = get_destination_column(
                    df_route, ctx.direction, ctx.focus_airport
                ).value_counts()
            _map_exclude = {ctx.focus_airport} if ctx.focus_airport else set()
            _render_route_top_airports_tab(
                df_route,
                _top_airport_counts,
                ctx.direction,
                ctx.focus_airport,
                ctx.geo_scope,
                ctx.top_n,
                ctx.start_date,
                ctx.end_date,
                map_exclude_iatas=_map_exclude,
            )

    if tab_route_airport_compare is not None:
        with tab_route_airport_compare:
            if route_by_province:
                _compare_caption = (
                    "Compare how flights are split across airports "
                    "within this province."
                )
                _compare_empty = "No airport traffic is available for this province."
                _share_scope = "province"
            else:
                _compare_caption = (
                    "Compare how flights are split across airports within "
                    "multi-airport cities."
                )
                _compare_empty = (
                    "No multi-airport city traffic is available for this route."
                )
                _share_scope = "city"
            st.caption(_compare_caption)
            _airport_compare_rows = []
            for row in df_route.itertuples(index=False):
                for airport in (row.origin, row.destination):
                    if route_by_province:
                        if airport not in _airport_compare_province_iatas:
                            continue
                        group_label = sel_region
                    else:
                        city_key = _airport_city_key(airport)
                        if city_key not in _airport_compare_city_keys:
                            continue
                        group_label = _city_key_label(city_key)
                    info = get_airport(airport)
                    _airport_compare_rows.append(
                        {
                            "Date": row.date.date(),
                            "Group": group_label,
                            "Airport": airport,
                            "Name": info.name if info else airport,
                            "Airline": getattr(row, ctx.airline_col),
                        }
                    )
            _airport_compare_df = pd.DataFrame(_airport_compare_rows)
            if _airport_compare_df.empty:
                st.caption(_compare_empty)
            else:
                _airport_counts = (
                    _airport_compare_df.groupby(
                        ["Group", "Airport", "Name"], as_index=False
                    )
                    .size()
                    .rename(columns={"size": "Flights"})
                )
                _airport_counts["Group total"] = _airport_counts.groupby("Group")[
                    "Flights"
                ].transform("sum")
                _airport_counts["Share (%)"] = (
                    100 * _airport_counts["Flights"] / _airport_counts["Group total"]
                ).round(1)
                _airport_counts["Share label"] = _airport_counts["Share (%)"].apply(
                    lambda x: f"{x}%"
                )
                _airport_counts["Label"] = (
                    _airport_counts["Airport"] + " - " + _airport_counts["Name"]
                )
                fig_airport_compare = px.bar(
                    _airport_counts.sort_values("Flights"),
                    x="Flights",
                    y="Label",
                    color="Group",
                    orientation="h",
                    labels={"Flights": "Number of flights"},
                    text="Share label",
                    custom_data=["Group", "Share (%)"],
                )
                _share_hover = (
                    "Province share" if _share_scope == "province" else "City share"
                )
                fig_airport_compare.update_traces(
                    hovertemplate=f"%{{customdata[0]}}<br>%{{y}}<br>Flights: %{{x:,}}<br>{_share_hover}: %{{customdata[1]}}%<extra></extra>",
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
                        ["Date", "Group", "Airport"], as_index=False
                    )
                    .size()
                    .rename(columns={"size": "Flights"})
                )
                _airport_daily["Airport label"] = (
                    _airport_daily["Group"] + " | " + _airport_daily["Airport"]
                )
                _airport_daily = _complete_daily_series(
                    _airport_daily,
                    date_col="Date",
                    value_cols=["Flights"],
                    start_date=ctx.start_date,
                    end_date=ctx.end_date,
                    group_cols=["Group", "Airport", "Airport label"],
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
                _airport_daily_share["Group total"] = _airport_daily_share.groupby(
                    ["Date", "Group"]
                )["Flights"].transform("sum")
                _airport_daily_share["Share (%)"] = np.where(
                    _airport_daily_share["Group total"] > 0,
                    100
                    * _airport_daily_share["Flights"]
                    / _airport_daily_share["Group total"],
                    0,
                ).round(1)
                _share_y_label = (
                    "Share of province flights (%)"
                    if _share_scope == "province"
                    else "Share of city flights (%)"
                )
                _share_chart_title = (
                    "Share of province flights per day by airport"
                    if _share_scope == "province"
                    else "Share of city flights per day by airport"
                )
                _share_total_label = (
                    "Province total" if _share_scope == "province" else "City total"
                )
                fig_airport_daily_share = px.line(
                    _airport_daily_share,
                    x="Date",
                    y="Share (%)",
                    color="Airport label",
                    labels={"Share (%)": _share_y_label},
                    custom_data=["Flights", "Group total"],
                )
                fig_airport_daily_share.update_traces(
                    hovertemplate=f"%{{fullData.name}}<br>%{{x}}<br>Flights: %{{customdata[0]:,}}<br>{_share_total_label}: %{{customdata[1]:,}}<br>Share: %{{y}}%<extra></extra>",
                )
                fig_airport_daily_share.update_layout(
                    height=350,
                    title=_share_chart_title,
                    yaxis=dict(title=_share_y_label, range=[0, 100]),
                )
                st.plotly_chart(fig_airport_daily_share, width="stretch")

                _airport_airline = (
                    _airport_compare_df.groupby(
                        ["Group", "Airport", "Airline"], as_index=False
                    )
                    .size()
                    .rename(columns={"size": "Flights"})
                )
                _airport_airline["Airline name"] = _airport_airline["Airline"].apply(
                    lambda c: get_airline(c).name if get_airline(c) else c
                )
                _airport_airline["Airport label"] = (
                    _airport_airline["Group"] + " | " + _airport_airline["Airport"]
                )
                _airport_airline = _airport_airline.sort_values(
                    "Flights", ascending=False
                ).head(ctx.top_n)
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

                _compare_table = _airport_counts.rename(
                    columns={"Group": "Province" if route_by_province else "City"}
                )
                _render_aggrid(
                    _compare_table[
                        [
                            "Province" if route_by_province else "City",
                            "Airport",
                            "Name",
                            "Flights",
                            "Share (%)",
                        ]
                    ]
                )

    with tab_route_airlines:
        airline_counts_route = df_route[ctx.airline_col].value_counts()
        total_on_route = len(df_route)
        airline_rows = []
        for icao, count in airline_counts_route.head(ctx.top_n).items():
            info = get_airline(icao)
            name = info.name if info else icao
            share = 100 * count / total_on_route if total_on_route > 0 else 0
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
                height=300 + min(ctx.top_n, len(airline_route_df)) * 12,
                yaxis={"categoryorder": "total ascending"},
                showlegend=False,
            )
            _start_flight_count_axis_at_zero(fig_route_airlines, "x")
            fig_route_airlines.update_traces(textposition="outside")
            st.plotly_chart(fig_route_airlines, width="stretch")

            top_airlines_route = set(airline_counts_route.head(ctx.top_n).index)
            by_date_airline = (
                df_route.groupby([df_route["date"].dt.date, ctx.airline_col])
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
                by_date_airline = _complete_daily_series(
                    by_date_airline,
                    date_col="Date",
                    value_cols=["Flights", "Total", "Share (%)"],
                    start_date=ctx.start_date,
                    end_date=ctx.end_date,
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

        _render_aggrid(
            airline_route_df[["Airline", "ICAO", "Flights", "Share (%)"]]
            if not airline_route_df.empty
            else pd.DataFrame()
        )

        st.subheader("Alliance share on this route")
        st.caption("Alliance from OpenTravelData members only — not from code-shares.")
        df_route_a = with_alliance_column(df_route, ctx.airline_col)
        alliance_counts_route = df_route_a["alliance"].value_counts()
        alliance_rows = []
        for alliance_id in ALLIANCE_ORDER:
            count = int(alliance_counts_route.get(alliance_id, 0))
            if count <= 0:
                continue
            share = 100 * count / total_on_route if total_on_route > 0 else 0
            alliance_rows.append(
                {
                    "Alliance": _alliance_label(alliance_id),
                    "Flights": count,
                    "Share (%)": round(share, 1),
                }
            )
        alliance_route_df = pd.DataFrame(alliance_rows)
        if not alliance_route_df.empty:
            fig_route_alliances = px.bar(
                alliance_route_df,
                x="Flights",
                y="Alliance",
                orientation="h",
                color="Share (%)",
                color_continuous_scale="Teal",
                range_color=[0, 100],
                text=alliance_route_df["Share (%)"].apply(lambda x: f"{x}%"),
            )
            fig_route_alliances.update_layout(
                height=280,
                yaxis={"categoryorder": "total ascending"},
                showlegend=False,
            )
            _start_flight_count_axis_at_zero(fig_route_alliances, "x")
            fig_route_alliances.update_traces(textposition="outside")
            st.plotly_chart(fig_route_alliances, width="stretch")
            _render_aggrid(alliance_route_df)
        else:
            st.caption("No alliance traffic on this route.")

    with tab_route_time:
        if render_primary_flights_over_time(df_route, ctx):
            top_airlines_route = set(airline_counts_route.head(ctx.top_n).index)
            total_per_date_route = (
                df_route.groupby(df_route["date"].dt.date).size().rename("Total")
            )
            render_secondary_grouped_over_time(
                df_route,
                ctx,
                group_values=df_route[ctx.airline_col],
                top_groups=top_airlines_route,
                group_key_col="ICAO",
                label_fn=lambda c: get_airline(c).name if get_airline(c) else c,
                color_col="Airline",
                title="Flights over time by airline",
                totals=total_per_date_route,
                totals_merge="date",
            )

    with tab_route_hour:
        render_scheduled_hour(df_route, ctx)

    with tab_route_weekday:
        render_weekday_average(df_route)

    if tab_route_cargo is not None:
        with tab_route_cargo:
            render_cargo_tab(df_route, ctx)
