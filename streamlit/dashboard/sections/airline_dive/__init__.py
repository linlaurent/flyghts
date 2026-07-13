"""Airline deep dive section."""

import pandas as pd

import streamlit as st
from flyghts.reference import get_airline

from ... import action_logger as al
from ...context import DashboardContext
from .comparison import render_airline_comparison
from .single_airline import render_single_airline_dive


def render_airline_dive(ctx: DashboardContext) -> None:
    st.header("Airline deep dive")
    dive_airlines = sorted(ctx.df[ctx.airline_col].dropna().unique().tolist())
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
            airline_search = al.text_input(
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
            if not ctx.is_us:
                for i, opt in enumerate(filtered_airlines):
                    if (
                        opt.startswith("CPA -")
                        or dive_display_to_code.get(opt) == "CPA"
                    ):
                        default_dive_idx = i
                        break

            with col_select_a:
                sel_dive_airline = al.selectbox(
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
                ctx.df[ctx.df[ctx.airline_col] == dive_icao]
                if dive_icao
                else pd.DataFrame()
            )

            if df_airline.empty:
                st.info("No flights for this airline in the selected filters.")
            else:
                render_single_airline_dive(
                    ctx,
                    df_airline=df_airline,
                    dive_icao=dive_icao,
                )

    render_airline_comparison(
        ctx,
        dive_airline_options=dive_airline_options,
        dive_display_to_code=dive_display_to_code,
    )
