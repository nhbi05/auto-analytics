"""Tests for consistent display and export chart styling."""

from __future__ import annotations

import unittest
from io import BytesIO

import plotly.graph_objects as go
from PIL import Image

from charts import PRIMARY_COLOR, style_chart
from exports import build_graph_download


class ChartStyleTests(unittest.TestCase):
    def test_export_preserves_display_bar_color_and_layout(self) -> None:
        figure = go.Figure(go.Bar(x=["Housing", "Investment"], y=[300, 500]))
        style_chart(
            figure,
            title="Target Amount by Purpose",
            chart_type="bar",
        )

        _filename, content = build_graph_download(
            figure,
            "Target Amount by Purpose",
        )

        self.assertEqual(figure.data[0].marker.color, PRIMARY_COLOR)
        self.assertEqual(figure.layout.title.text, "Target Amount by Purpose")
        self.assertTrue(figure.layout.xaxis.automargin)
        self.assertTrue(figure.layout.yaxis.automargin)
        with Image.open(BytesIO(content)) as image:
            colors = image.convert("RGB").getcolors(maxcolors=2_000_000)
        self.assertIsNotNone(colors)
        primary_rgb = (0, 104, 201)
        primary_pixels = sum(
            count for count, color in colors or [] if color == primary_rgb
        )
        self.assertGreater(primary_pixels, 1_000)


if __name__ == "__main__":
    unittest.main()
