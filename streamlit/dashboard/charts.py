"""Chart utilities and overview chart rendering."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from flyghts.reference import get_airline


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


def _render_overview_flights_per_day(
    df: pd.DataFrame,
    *,
    airline_col: str,
    top_n: int,
    start_date,
    end_date,
) -> None:
    """Render overview daily flight totals with top-airline breakdown."""
    st.subheader("Flights per day")
    flights_per_day = df.groupby(df["date"].dt.date).size().reset_index(name="Flights")
    flights_per_day.columns = ["Date", "Flights"]
    flights_per_day = _complete_daily_series(
        flights_per_day,
        date_col="Date",
        value_cols=["Flights"],
        start_date=start_date,
        end_date=end_date,
    )
    if flights_per_day.empty:
        st.caption("No date data.")
        return

    total_avg = round(flights_per_day["Flights"].mean(), 1)
    total_label = f"Total ({total_avg:.1f} avg/day)"
    total_series = flights_per_day.assign(Airline=total_label)

    top_airline_codes = set(df[airline_col].value_counts().head(top_n).index)
    by_date_airline = (
        df.groupby([df["date"].dt.date, airline_col]).size().reset_index(name="Flights")
    )
    by_date_airline.columns = ["Date", "ICAO", "Flights"]
    by_date_airline = by_date_airline[by_date_airline["ICAO"].isin(top_airline_codes)]
    by_date_airline["Airline"] = by_date_airline["ICAO"].apply(
        lambda c: get_airline(c).name if get_airline(c) else c
    )
    by_date_airline = _complete_daily_series(
        by_date_airline,
        date_col="Date",
        value_cols=["Flights"],
        start_date=start_date,
        end_date=end_date,
        group_cols=["ICAO", "Airline"],
    )
    airline_avgs = (
        by_date_airline.groupby("Airline")["Flights"]
        .mean()
        .round(1)
        .sort_values(ascending=False)
    )
    airline_label_map = {
        name: f"{name} ({avg:.1f} avg/day)" for name, avg in airline_avgs.items()
    }
    by_date_airline["Airline"] = by_date_airline["Airline"].map(airline_label_map)
    combined = pd.concat(
        [
            total_series[["Date", "Flights", "Airline"]],
            by_date_airline[["Date", "Flights", "Airline"]],
        ],
        ignore_index=True,
    )
    color_order = [
        total_label,
        *[airline_label_map[name] for name in airline_avgs.index],
    ]

    fig_per_day = px.line(
        combined,
        x="Date",
        y="Flights",
        color="Airline",
        labels={"Date": "Date", "Flights": "Number of flights"},
        category_orders={"Airline": color_order},
    )
    fig_per_day.update_layout(height=350)
    _start_flight_count_axis_at_zero(fig_per_day, "y")
    st.plotly_chart(fig_per_day, width="stretch")


def _render_overview_flights_per_day_by_alliance(
    df: pd.DataFrame,
    *,
    airline_col: str,
    start_date,
    end_date,
) -> None:
    """Render daily flights broken down by OPTD alliance (not code-shares)."""
    from .formatting import (
        ALLIANCE_ORDER,
        _alliance_label,
        with_alliance_column,
    )

    st.subheader("Flights per day by alliance")
    df_a = with_alliance_column(df, airline_col)
    by_date = (
        df_a.groupby([df_a["date"].dt.date, "alliance"])
        .size()
        .reset_index(name="Flights")
    )
    by_date.columns = ["Date", "alliance", "Flights"]
    by_date["Alliance"] = by_date["alliance"].map(_alliance_label)
    by_date = _complete_daily_series(
        by_date,
        date_col="Date",
        value_cols=["Flights"],
        start_date=start_date,
        end_date=end_date,
        group_cols=["alliance", "Alliance"],
    )
    if by_date.empty:
        st.caption("No date data.")
        return

    present = [a for a in ALLIANCE_ORDER if a in set(by_date["alliance"])]
    label_order = [_alliance_label(a) for a in present]
    fig = px.line(
        by_date,
        x="Date",
        y="Flights",
        color="Alliance",
        labels={"Date": "Date", "Flights": "Number of flights"},
        category_orders={"Alliance": label_order},
    )
    fig.update_layout(height=350)
    _start_flight_count_axis_at_zero(fig, "y")
    st.plotly_chart(fig, width="stretch")
