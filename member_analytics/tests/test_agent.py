"""Regression tests for generated SQL execution."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import pandas as pd

from agent import (
    _allows_non_successful_amount,
    _chart_settings,
    _contains_numeric_literal,
    _is_grouping_error,
    _projection_window,
    _projection_periods,
    _requests_projection,
    ask_database,
)


class _PostgresGroupingError(Exception):
    sqlstate = "42803"


class _DatabaseError(Exception):
    def __init__(self) -> None:
        self.orig = _PostgresGroupingError()


class GeneratedQueryTests(unittest.TestCase):
    def test_historical_trend_is_not_projection_intent(self) -> None:
        self.assertFalse(
            _requests_projection(
                "Show monthly enrollment trends for 2023 and 2024."
            )
        )
        self.assertTrue(
            _requests_projection(
                "Project monthly enrollment for the next 6 months."
            )
        )
        self.assertEqual(
            _projection_periods(
                {"projection_periods": 6},
                "Which channel will lead next month?",
            ),
            1,
        )
        first_target, calculation_periods = _projection_window(
            pd.DataFrame(
                {"period": pd.date_range("2026-01-01", periods=6, freq="MS")}
            ),
            1,
            current_date=pd.Timestamp("2026-07-29"),
        )
        self.assertEqual(first_target, pd.Timestamp("2026-08-01"))
        self.assertEqual(calculation_periods, 2)

    def test_accepts_requested_pie_chart(self) -> None:
        data = pd.DataFrame(
            {"label": ["MTN", "Airtel"], "value": [139357, 88433]}
        )
        payload = {
            "chart_type": "pie",
            "x_column": "label",
            "y_column": "value",
            "chart_title": "MTN versus Airtel members",
        }

        settings = _chart_settings(payload, data)

        self.assertEqual(
            settings,
            ("pie", "label", "value", "MTN versus Airtel members"),
        )

    def test_accepts_other_supported_chart_types(self) -> None:
        paired_data = pd.DataFrame(
            {"label": ["A", "B", "C"], "value": [10, 15, 12]}
        )
        for chart_type in (
            "bar",
            "line",
            "donut",
            "area",
            "scatter",
            "funnel",
        ):
            with self.subTest(chart_type=chart_type):
                settings = _chart_settings(
                    {
                        "chart_type": chart_type,
                        "x_column": "label",
                        "y_column": "value",
                        "chart_title": "Test chart",
                    },
                    paired_data,
                )
                self.assertEqual(
                    settings,
                    (chart_type, "label", "value", "Test chart"),
                )

        numeric_data = pd.DataFrame({"amount": [10, 12, 18, 25]})
        for chart_type in ("histogram", "box"):
            with self.subTest(chart_type=chart_type):
                settings = _chart_settings(
                    {
                        "chart_type": chart_type,
                        "x_column": "amount",
                        "y_column": "",
                        "chart_title": "Amount distribution",
                    },
                    numeric_data,
                )
                self.assertEqual(
                    settings,
                    (chart_type, "amount", "", "Amount distribution"),
                )

    def test_only_explicit_status_analysis_can_include_unsuccessful_amounts(
        self,
    ) -> None:
        self.assertFalse(_allows_non_successful_amount("Project monthly income"))
        self.assertTrue(_allows_non_successful_amount("Show failed amounts"))
        self.assertTrue(_allows_non_successful_amount("Compare amount by status"))

    def test_recognizes_equivalent_target_limit_literals(self) -> None:
        self.assertTrue(
            _contains_numeric_literal(
                "WHERE target_value <= 1e10",
                "10000000000",
            )
        )

    def test_finds_grouping_sqlstate_in_wrapped_exception(self) -> None:
        self.assertTrue(_is_grouping_error(_DatabaseError()))
        self.assertFalse(_is_grouping_error(ValueError("different error")))

    @patch("agent._schema_text", return_value="- record_date: date")
    @patch("agent.table_name", return_value="member_accounts")
    @patch("agent.run_readonly_query")
    @patch("agent._chat")
    def test_repairs_ambiguous_group_by_alias_once(
        self,
        chat,
        run_query,
        _table_name,
        _schema,
    ) -> None:
        generated = {
            "sql": (
                "SELECT DATE_TRUNC('month', record_date) AS period, "
                "COUNT(*) AS value FROM member_accounts GROUP BY period"
            ),
            "reasoning": "Monthly totals",
            "analysis_type": "query",
            "projection_periods": 6,
            "chart_type": "none",
            "x_column": "",
            "y_column": "",
            "chart_title": "",
        }
        repaired = {
            **generated,
            "sql": generated["sql"].replace("GROUP BY period", "GROUP BY 1"),
        }
        chat.side_effect = [
            json.dumps(generated),
            json.dumps(repaired),
            "Two monthly totals were returned.",
        ]
        run_query.side_effect = [
            _DatabaseError(),
            pd.DataFrame(
                {
                    "period": pd.to_datetime(["2026-05-01", "2026-06-01"]),
                    "value": [10, 12],
                }
            ),
        ]

        result = ask_database("Show monthly registrations")

        self.assertIn("GROUP BY 1", result.sql)
        self.assertEqual(run_query.call_count, 2)
        self.assertIn("SQLSTATE 42803", chat.call_args_list[1].args[1])

    @patch("agent._schema_text", return_value="- amount: numeric\n- status: text")
    @patch("agent.table_name", return_value="member_accounts")
    @patch("agent.run_readonly_query")
    @patch("agent._chat")
    def test_repairs_monetary_query_without_success_filter(
        self,
        chat,
        run_query,
        _table_name,
        _schema,
    ) -> None:
        generated = {
            "sql": "SELECT SUM(amount) AS value FROM member_accounts",
            "reasoning": "Total income",
            "analysis_type": "query",
            "projection_periods": 6,
            "chart_type": "none",
            "x_column": "",
            "y_column": "",
            "chart_title": "",
        }
        repaired = {
            **generated,
            "sql": (
                "SELECT SUM(amount) AS value FROM member_accounts "
                "WHERE LOWER(status) = LOWER('SUCCESS')"
            ),
        }
        chat.side_effect = [
            json.dumps(generated),
            json.dumps(repaired),
            "Successful income is 250.",
        ]
        run_query.return_value = pd.DataFrame({"value": [250]})

        result = ask_database("What is the total income?")

        self.assertIn("'SUCCESS'", result.sql)
        run_query.assert_called_once_with(repaired["sql"])
        self.assertIn(
            "business or data-quality rules",
            chat.call_args_list[1].args[1],
        )

    @patch(
        "agent._schema_text",
        return_value=(
            "- account_purpose: text\n"
            "- target_amount: text\n"
            "- status: text"
        ),
    )
    @patch("agent.table_name", return_value="member_accounts")
    @patch("agent.run_readonly_query")
    @patch("agent._chat")
    def test_repairs_target_amount_query_with_quality_rules(
        self,
        chat,
        run_query,
        _table_name,
        _schema,
    ) -> None:
        generated = {
            "sql": (
                "SELECT account_purpose AS label, "
                "SUM(target_amount::numeric) AS value "
                "FROM member_accounts GROUP BY 1"
            ),
            "reasoning": "Target totals by purpose",
            "analysis_type": "query",
            "projection_periods": 6,
            "chart_type": "bar",
            "x_column": "label",
            "y_column": "value",
            "chart_title": "Target amount by purpose",
        }
        repaired = {
            **generated,
            "sql": (
                "WITH parsed AS ("
                "SELECT account_purpose, "
                "CASE WHEN TRIM(target_amount) ~ "
                "'^[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$' "
                "THEN TRIM(target_amount)::numeric END AS target_value "
                "FROM member_accounts "
                "WHERE LOWER(status) = LOWER('SUCCESS')) "
                "SELECT account_purpose AS label, SUM(target_value) AS value "
                "FROM parsed "
                "WHERE target_value BETWEEN 0 AND 10000000000 "
                "GROUP BY 1"
            ),
        }
        chat.side_effect = [
            json.dumps(generated),
            json.dumps(repaired),
            "Financial Independence has the largest valid target total.",
        ]
        run_query.return_value = pd.DataFrame(
            {
                "label": ["FinancialIndependence", "Investment"],
                "value": [529_062_700_000, 501_178_400_000],
            }
        )

        result = ask_database("Graph total target amount by account purpose")

        self.assertIn("10000000000", result.sql)
        self.assertIn("'SUCCESS'", result.sql)
        self.assertIn("~", result.sql)
        run_query.assert_called_once_with(repaired["sql"])

    @patch("agent._schema_text", return_value="- record_date: date")
    @patch("agent.table_name", return_value="member_accounts")
    @patch("agent.run_readonly_query")
    @patch("agent._chat")
    def test_model_cannot_turn_historical_trend_into_projection(
        self,
        chat,
        run_query,
        _table_name,
        _schema,
    ) -> None:
        generated = {
            "sql": (
                "SELECT DATE_TRUNC('month', record_date) AS period, "
                "COUNT(*) AS value FROM member_accounts "
                "WHERE record_date >= DATE '2023-01-01' "
                "AND record_date < DATE '2025-01-01' GROUP BY 1 ORDER BY 1"
            ),
            "reasoning": "Monthly historical trend",
            "analysis_type": "projection",
            "projection_periods": 6,
            "chart_type": "line",
            "x_column": "period",
            "y_column": "value",
            "chart_title": "Monthly Enrollment Trends for 2023 and 2024",
        }
        chat.side_effect = [
            json.dumps(generated),
            "Enrollment varied across the two historical years.",
        ]
        run_query.return_value = pd.DataFrame(
            {
                "period": pd.date_range("2023-01-01", periods=24, freq="MS"),
                "value": list(range(24)),
            }
        )

        result = ask_database(
            "Show monthly enrollment trends for 2023 and 2024."
        )

        self.assertEqual(result.analysis_type, "query")
        self.assertEqual(result.chart_type, "line")
        self.assertEqual(result.y_column, "value")
        self.assertEqual(len(result.data), 24)

    @patch(
        "agent._schema_text",
        return_value="- record_date: date\n- channel: text",
    )
    @patch("agent.table_name", return_value="member_accounts")
    @patch("agent.run_readonly_query")
    @patch("agent._chat")
    def test_repairs_and_runs_grouped_channel_projection(
        self,
        chat,
        run_query,
        _table_name,
        _schema,
    ) -> None:
        generated = {
            "sql": (
                "SELECT channel, COUNT(*) AS value "
                "FROM member_accounts GROUP BY 1"
            ),
            "reasoning": "Channel totals",
            "analysis_type": "projection",
            "projection_periods": 6,
            "chart_type": "line",
            "x_column": "period",
            "y_column": "value",
            "chart_title": "Expected Enrollments by Channel",
        }
        repaired = {
            **generated,
            "sql": (
                "SELECT DATE_TRUNC('month', record_date) AS period, "
                "channel AS series, COUNT(*) AS value "
                "FROM member_accounts GROUP BY 1, 2 ORDER BY 1, 2"
            ),
            "projection_periods": 1,
        }
        chat.side_effect = [
            json.dumps(generated),
            json.dumps(repaired),
            "Mobile is expected to have the most enrollments next month.",
        ]
        run_query.side_effect = [
            pd.DataFrame({"channel": ["Branch", "Mobile"], "value": [20, 30]}),
            pd.DataFrame(
                {
                    "period": list(
                        pd.date_range("2026-01-01", periods=4, freq="MS")
                    )
                    * 2,
                    "series": ["Branch"] * 4 + ["Mobile"] * 4,
                    "value": [30, 31, 32, 33, 40, 45, 50, 55],
                }
            ),
        ]

        result = ask_database(
            "Which channel is expected to have the most enrollments next month?"
        )

        self.assertEqual(result.analysis_type, "projection")
        self.assertEqual(set(result.data["series"]), {"Branch", "Mobile"})
        self.assertEqual(len(result.data), 2)
        self.assertIn("series", result.chart_data.columns)
        self.assertEqual(run_query.call_count, 2)
        self.assertIn(
            '"period", "series", and "value"',
            chat.call_args_list[1].args[1],
        )


if __name__ == "__main__":
    unittest.main()
