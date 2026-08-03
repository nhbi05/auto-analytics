"""Predefined analytical queries for the dashboard."""

from __future__ import annotations

import os

import pandas as pd

from database import column_name, quote_identifier, run_query, table_name


def _table() -> str:
    return quote_identifier(table_name())


def _column(setting: str, default: str) -> str:
    return quote_identifier(column_name(setting, default))


def get_summary_metrics() -> dict[str, float | int]:
    status = _column("STATUS_COLUMN", "status")
    amount = _column("AMOUNT_COLUMN", "amount")
    cleaned_amount = (
        f"REGEXP_REPLACE(CAST({amount} AS TEXT), '[^0-9.-]', '', 'g')"
    )
    result = run_query(
        f"""
        SELECT
            COUNT(*) AS total_accounts,
            COUNT(*) FILTER (WHERE LOWER(CAST({status} AS TEXT)) = LOWER(:approved)) AS approved,
            COUNT(*) FILTER (WHERE LOWER(CAST({status} AS TEXT)) = LOWER(:pending)) AS pending,
            COUNT(*) FILTER (WHERE LOWER(CAST({status} AS TEXT)) = LOWER(:rejected)) AS rejected,
            COALESCE(
                SUM(
                    CASE
                        WHEN LOWER(CAST({status} AS TEXT)) = LOWER(:approved)
                         AND {cleaned_amount} ~ '^-?[0-9]+(\\.[0-9]+)?$'
                        THEN {cleaned_amount}::numeric
                        ELSE 0
                    END
                ),
                0
            ) AS total_amount
        FROM {_table()}
        """,
        {
            "approved": os.getenv("APPROVED_VALUE", "approved"),
            "pending": os.getenv("PENDING_VALUE", "pending"),
            "rejected": os.getenv("REJECTED_VALUE", "rejected"),
        },
    )
    row = result.iloc[0]
    return {
        "total_accounts": int(row["total_accounts"] or 0),
        "approved": int(row["approved"] or 0),
        "pending": int(row["pending"] or 0),
        "rejected": int(row["rejected"] or 0),
        "total_amount": float(row["total_amount"] or 0),
    }


def get_status_distribution() -> pd.DataFrame:
    status = _column("STATUS_COLUMN", "status")
    return run_query(
        f"""
        SELECT COALESCE(CAST({status} AS TEXT), 'Unknown') AS status, COUNT(*) AS accounts
        FROM {_table()}
        GROUP BY 1
        ORDER BY accounts DESC
        """
    )


def get_network_distribution() -> pd.DataFrame:
    network = _column("NETWORK_COLUMN", "network")
    return run_query(
        f"""
        SELECT COALESCE(CAST({network} AS TEXT), 'Unknown') AS network, COUNT(*) AS accounts
        FROM {_table()}
        GROUP BY 1
        ORDER BY accounts DESC
        LIMIT 12
        """
    )


def get_channel_distribution() -> pd.DataFrame:
    channel = _column("CHANNEL_COLUMN", "channel")
    return run_query(
        f"""
        SELECT COALESCE(CAST({channel} AS TEXT), 'Unknown') AS channel, COUNT(*) AS accounts
        FROM {_table()}
        GROUP BY 1
        ORDER BY accounts DESC
        LIMIT 12
        """
    )


def get_monthly_registrations() -> pd.DataFrame:
    created_at = _column("CREATED_AT_COLUMN", "created_at")
    return run_query(
        f"""
        SELECT DATE_TRUNC('month', {created_at})::date AS month, COUNT(*) AS registrations
        FROM {_table()}
        WHERE {created_at} IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        """
    )


def _benefits_table() -> str:
    return quote_identifier(
        os.getenv("BENEFITS_TABLE", "public.smartlife_contributions")
    )


def get_benefits_summary() -> dict[str, float | int]:
    result = run_query(
        f"""
        SELECT
            COUNT(*) AS total_contributions,
            COUNT(DISTINCT nssf_number) AS contributing_members,
            COUNT(*) FILTER (WHERE UPPER(COALESCE(status, '')) = 'SUCCESS') AS successful,
            COUNT(*) FILTER (WHERE UPPER(COALESCE(status, '')) = 'PENDING') AS pending,
            COALESCE(
                SUM(paid_amount) FILTER (
                    WHERE UPPER(COALESCE(status, '')) = 'SUCCESS'
                ),
                0
            ) AS total_paid
        FROM {_benefits_table()}
        """
    )
    row = result.iloc[0]
    return {
        "total_contributions": int(row["total_contributions"] or 0),
        "contributing_members": int(row["contributing_members"] or 0),
        "successful": int(row["successful"] or 0),
        "pending": int(row["pending"] or 0),
        "total_paid": float(row["total_paid"] or 0),
    }


def get_benefits_status_distribution() -> pd.DataFrame:
    return run_query(
        f"""
        SELECT COALESCE(status, 'Unknown') AS status, COUNT(*) AS contributions
        FROM {_benefits_table()}
        GROUP BY 1
        ORDER BY contributions DESC
        """
    )


def get_benefits_vendor_distribution() -> pd.DataFrame:
    return run_query(
        f"""
        SELECT COALESCE(vendor, 'Unknown') AS vendor, COUNT(*) AS contributions
        FROM {_benefits_table()}
        GROUP BY 1
        ORDER BY contributions DESC
        LIMIT 12
        """
    )


def get_monthly_benefits() -> pd.DataFrame:
    return run_query(
        f"""
        SELECT
            DATE_TRUNC('month', record_date)::date AS month,
            COUNT(*) AS contributions,
            COALESCE(
                SUM(paid_amount) FILTER (
                    WHERE UPPER(COALESCE(status, '')) = 'SUCCESS'
                ),
                0
            ) AS paid_amount
        FROM {_benefits_table()}
        WHERE record_date IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        """
    )
