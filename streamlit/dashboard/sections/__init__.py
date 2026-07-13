"""Dashboard section dispatch."""

from ..context import DashboardContext
from .airline_dive import render_airline_dive
from .alliance_dive import render_alliance_dive
from .delay import render_delay_analysis
from .insights import render_insights
from .overview import render_overview
from .route_dive import render_route_dive

__all__ = [
    "dispatch_section",
    "render_airline_dive",
    "render_alliance_dive",
    "render_delay_analysis",
    "render_insights",
    "render_overview",
    "render_route_dive",
]


def dispatch_section(ctx: DashboardContext) -> None:
    """Render the sidebar-selected dashboard section."""
    if ctx.section == "Overview":
        render_overview(ctx)
    elif ctx.section == "Insights":
        render_insights(ctx)
    elif ctx.section == "Airline deep dive":
        render_airline_dive(ctx)
    elif ctx.section == "Alliance deep dive":
        render_alliance_dive(ctx)
    elif ctx.section == "Route deep dive":
        render_route_dive(ctx)
    elif ctx.section == "Delay analysis":
        render_delay_analysis(ctx)
