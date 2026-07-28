"""Download helpers for generated analytics charts."""

from __future__ import annotations

import re

import plotly.graph_objects as go


def build_graph_download(
    figure: go.Figure,
    title: str,
) -> tuple[str, bytes]:
    """Return a safe filename and PNG image for a Plotly figure."""
    filename_stem = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    filename = f"{filename_stem or 'analytics-graph'}.png"

    export_figure = go.Figure(figure)
    export_figure.update_layout(
        width=1600,
        height=700,
    )
    content = export_figure.to_image(
        format="png",
        width=1600,
        height=700,
        scale=1,
    )
    return filename, content
