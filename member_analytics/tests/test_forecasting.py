"""Tests for projection value formatting."""

from __future__ import annotations

import unittest

import pandas as pd

from forecasting import grouped_monthly_forecast, linear_monthly_forecast


class ForecastingTests(unittest.TestCase):
    def test_projects_each_series_independently(self) -> None:
        periods = pd.date_range("2026-01-01", periods=4, freq="MS")
        history = pd.DataFrame(
            {
                "period": list(periods) * 2,
                "series": ["Branch"] * 4 + ["Mobile"] * 4,
                "value": [30, 31, 32, 33, 40, 45, 50, 55],
            }
        )

        result = grouped_monthly_forecast(
            history,
            date_column="period",
            series_column="series",
            value_column="value",
            periods=1,
        )

        projected = result.forecast.set_index("series")["projected_value"]
        self.assertEqual(projected["Branch"], 34)
        self.assertEqual(projected["Mobile"], 60)
        self.assertEqual(set(result.chart_data["series"]), {"Branch", "Mobile"})

    def test_projected_counts_are_whole_numbers(self) -> None:
        history = pd.DataFrame(
            {
                "period": pd.to_datetime(
                    ["2026-01-01", "2026-02-01", "2026-03-01"]
                ),
                "value": [10, 11, 13],
            }
        )

        result = linear_monthly_forecast(
            history,
            date_column="period",
            value_column="value",
            periods=2,
        )

        self.assertEqual(result.forecast["projected_value"].tolist(), [14, 16])
        self.assertTrue(
            pd.api.types.is_integer_dtype(result.forecast["projected_value"])
        )


if __name__ == "__main__":
    unittest.main()
