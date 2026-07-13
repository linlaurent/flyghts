"""Alliance deep dive section (OPTD membership only; never from code-shares)."""

import streamlit as st

from ... import action_logger as al
from ...context import DashboardContext
from ...formatting import (
    ALLIANCE_ORDER,
    INDEPENDENT_ALLIANCE,
    _alliance_label,
    with_alliance_column,
)
from .comparison import render_alliance_comparison
from .single_alliance import render_single_alliance_dive


def render_alliance_dive(ctx: DashboardContext) -> None:
    st.header("Alliance deep dive")
    st.caption(
        "Alliance membership from OpenTravelData (full members only). "
        "Not inferred from marketing vs operating code-shares."
    )

    df_a = with_alliance_column(ctx.df, ctx.airline_col)
    options = [a for a in ALLIANCE_ORDER if int((df_a["alliance"] == a).sum()) > 0]
    if not options:
        options = list(ALLIANCE_ORDER)

    display_options = [_alliance_label(a) for a in options]
    display_to_id = {_alliance_label(a): a for a in options}

    sel_display = al.selectbox(
        "Select alliance",
        options=display_options,
        index=0,
        help="Explore traffic for one alliance under current filters.",
        key="alliance_dive_select",
    )
    dive_id = display_to_id.get(sel_display, options[0])
    df_alliance = df_a[df_a["alliance"] == dive_id]

    if df_alliance.empty:
        st.info("No flights for this alliance in the selected filters.")
    else:
        render_single_alliance_dive(
            ctx,
            df_alliance=df_alliance,
            alliance_id=dive_id,
        )

    render_alliance_comparison(ctx, df_all=df_a)
