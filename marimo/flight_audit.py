"""
Flight Traffic Audit - Interactive GUI

Run with: marimo edit marimo/flight_audit.py
Or: marimo run marimo/flight_audit.py
"""

import marimo

__generated_with = "0.19.11"
app = marimo.App()


@app.cell
def _imports():
    from datetime import date
    from typing import Optional

    import marimo as mo
    import pandas as pd
    import plotly.express as px

    from flyghts.audit.models import DateFilter, RouteFilter
    from flyghts.audit.service import AuditService

    return AuditService, DateFilter, Optional, RouteFilter, date, mo, pd, px


@app.cell
def _inputs(date, mo):
    route_input = mo.ui.text(
        value="HKG-TPE",
        label="Route (ORIGIN-DEST)",
        kind="area",
    )
    query_mode = mo.ui.radio(
        options=["single_date", "past_days"],
        value="single_date",
        label="Query by",
    )
    single_date = mo.ui.date(
        value=date.today().isoformat(),
        label="Date",
    )
    past_days = mo.ui.number(
        start=1,
        stop=365,
        step=1,
        value=7,
        label="Past N days",
    )
    run_btn = mo.ui.run_button(label="Run audit")
    return past_days, query_mode, route_input, run_btn, single_date


@app.cell
def _(route_input):
    route_input
    return


@app.cell
def _():
    return


@app.cell
def _form(mo, past_days, query_mode, route_input, run_btn, single_date):
    title = (
        "# Flight Traffic Audit\n\n"
        "Query and analyze flight traffic between routes (e.g. Hong Kong ↔ Taipei). "
        "Data source: Hong Kong International Airport Open API."
    )
    mo.vstack(
        [
            mo.md(title).center(),
            mo.hstack(
                [route_input, query_mode, single_date, past_days, run_btn],
                justify="start",
                wrap=True,
                gap=2,
            ),
        ],
        gap=2,
    )
    return


@app.cell
def _query(
    AuditService,
    DateFilter,
    Optional,
    RouteFilter,
    date,
    past_days,
    pd,
    query_mode,
    route_input,
    run_btn,
    single_date,
):
    _ = run_btn.value  # Re-run when Run audit is clicked

    route_str: str = route_input.value
    use_single: bool = query_mode.value == "single_date"
    if use_single:
        qdate_val = single_date.value
        qdate = date.fromisoformat(qdate_val) if isinstance(qdate_val, str) else qdate_val
        date_filter = DateFilter.single(qdate)
    else:
        n = int(past_days.value or 7)
        date_filter = DateFilter.past_days(n)

    result = None
    stats = None
    err_msg: Optional[str] = None
    try:
        route = RouteFilter.from_route_string(route_str)
        service = AuditService()
        result = service.query(route, date_filter)
        stats = service.statistics(result.flights) if result.flights else None
    except ValueError as e:
        err_msg = str(e)

    df = result.to_dataframe() if result else pd.DataFrame()
    return df, err_msg, result, stats


@app.cell
def _table(df, err_msg: "Optional[str]", mo, result):
    mo.md("## Flights").center()
    if err_msg:
        mo.md(f"Invalid input: {err_msg}").center()
    elif not result or not result.flights:
        mo.md("No flights found.").center()
    else:
        mo.ui.table(df, pagination=True)
    return


@app.cell
def _statistics(mo, pd, px, stats):
    if stats and stats.total_flights > 0:
        mo.md("## Statistics").center()
        stat_items = [
            mo.md(f"**Total flights:** {stats.total_flights}"),
            mo.md("### By airline").center(),
            mo.ui.table(stats.airline_dataframe()),
            mo.md("### By route").center(),
            mo.ui.table(
                pd.DataFrame(
                    [
                        {"route": k, "count": v}
                        for k, v in sorted(stats.by_route.items())
                    ]
                )
            ),
            mo.md("### Flights per hour").center(),
        ]
        mo.vstack(stat_items, gap=2)
        if stats.by_hour:
            hourly_df = stats.hourly_dataframe()
            fig = px.bar(
                hourly_df,
                x="hour",
                y="count",
                labels={"hour": "Hour (local)", "count": "Flights"},
                title="Flights by hour",
            )
            mo.ui.plotly(fig)
    return


if __name__ == "__main__":
    app.run()
