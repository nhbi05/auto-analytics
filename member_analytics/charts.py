"""Shared styling for displayed and downloaded analytics charts."""

from __future__ import annotations

import plotly.graph_objects as go

PRIMARY_COLOR = "#0068c9"
CHART_COLORS = (
    PRIMARY_COLOR,
    "#21a179",
    "#da7b35",
    "#7a5ea8",
    "#c94b4b",
    "#4c8b8b",
    "#9b7b2f",
    "#68758a",
)


def style_chart(
    figure: go.Figure,
    *,
    title: str,
    chart_type: str,
) -> go.Figure:
    """Apply a deterministic theme shared by the UI and PNG export."""
    figure.update_layout(
        template="plotly_white",
        title={
            "text": title,
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 20, "color": "#31333f"},
        },
        height=600,
        margin={"l": 90, "r": 30, "t": 70, "b": 130},
        paper_bgcolor="white",
        plot_bgcolor="white",
        font={"family": "Arial, sans-serif", "size": 14, "color": "#31333f"},
        colorway=list(CHART_COLORS),
        hoverlabel={"font": {"family": "Arial, sans-serif", "size": 14}},
    )
    figure.update_xaxes(
        automargin=True,
        gridcolor="#e6e9ef",
        linecolor="#9aa1aa",
        tickangle=35 if chart_type in {"bar", "box"} else 0,
    )
    figure.update_yaxes(
        automargin=True,
        gridcolor="#e6e9ef",
        linecolor="#9aa1aa",
    )

    if chart_type not in {"projection", "pie", "donut"}:
        for trace in figure.data:
            if trace.type in {"bar", "histogram"}:
                trace.marker.color = PRIMARY_COLOR
            elif trace.type == "scatter":
                trace.marker.color = PRIMARY_COLOR
                trace.line.color = PRIMARY_COLOR
            elif trace.type == "box":
                trace.marker.color = PRIMARY_COLOR
                trace.line.color = PRIMARY_COLOR
    return figure
