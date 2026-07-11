"""Reusable Streamlit table components."""

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder

from .formatting import _format_insight_table


def _render_aggrid(df: pd.DataFrame, *, height: int | None = None) -> None:
    """Render a dataframe with AgGrid columns that expand to fill width."""
    if df.empty:
        return

    gb = GridOptionsBuilder.from_dataframe(df)
    # Prefer flex over autoSizeStrategy=fitGridWidth: the one-shot fit can lock
    # tiny widths before the Streamlit component iframe finishes sizing.
    gb.configure_default_column(
        sortable=True,
        filter=True,
        resizable=True,
        flex=1,
        minWidth=100,
    )
    if "Airline" in df.columns:
        gb.configure_column("Airline", flex=2, minWidth=150)
    if "Route" in df.columns:
        gb.configure_column("Route", flex=3, minWidth=220)
    grid_options = gb.build()
    grid_options.pop("autoSizeStrategy", None)
    AgGrid(
        df,
        gridOptions=grid_options,
        height=height if height is not None else min(420, 80 + 35 * len(df)),
    )


def _render_insight_grid(title: str, df: pd.DataFrame, empty_message: str) -> None:
    st.subheader(title)
    if df.empty:
        st.caption(empty_message)
        return

    _render_aggrid(_format_insight_table(df))
