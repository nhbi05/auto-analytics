"""Tests for predefined dashboard metrics."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from analytics import get_summary_metrics


class SummaryMetricTests(unittest.TestCase):
    @patch("analytics.run_query")
    def test_collected_amount_uses_only_approved_status(self, run_query) -> None:
        run_query.return_value = pd.DataFrame(
            [
                {
                    "total_accounts": 4,
                    "approved": 1,
                    "pending": 1,
                    "rejected": 2,
                    "total_amount": 250,
                }
            ]
        )

        metrics = get_summary_metrics()

        sql = run_query.call_args.args[0]
        params = run_query.call_args.args[1]
        approved_filter = (
            'LOWER(CAST("status" AS TEXT)) = LOWER(:approved)'
        )
        self.assertEqual(sql.count(approved_filter), 2)
        self.assertEqual(params["approved"], "SUCCESS")
        self.assertEqual(metrics["total_amount"], 250.0)


if __name__ == "__main__":
    unittest.main()
