"""Tests for chart downloads."""

from __future__ import annotations

import unittest
from io import BytesIO

import plotly.graph_objects as go
from PIL import Image

from exports import build_graph_download


class GraphExportTests(unittest.TestCase):
    def test_builds_png_graph_with_safe_filename(self) -> None:
        figure = go.Figure(go.Bar(x=["Success"], y=[1250]))

        filename, content = build_graph_download(
            figure,
            "Monthly Income / Success",
        )

        self.assertEqual(filename, "monthly-income-success.png")
        self.assertTrue(content.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(BytesIO(content)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (1600, 700))


if __name__ == "__main__":
    unittest.main()
