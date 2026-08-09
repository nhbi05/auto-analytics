import json
import os
from decimal import Decimal

import pandas as pd

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "member_analytics_project.settings")

import django

django.setup()

from django.test import Client

from agent import AgentResult
from analytics_api import views


client = Client(HTTP_HOST="localhost")


def test_dashboard_serializes_dataframes(monkeypatch):
    monkeypatch.setattr(views, "_dashboard_cache", None)
    monkeypatch.setattr(views, "get_summary_metrics", lambda: {"total_accounts": 2})
    monkeypatch.setattr(
        views,
        "get_status_distribution",
        lambda: pd.DataFrame([{"status": "approved", "accounts": 2}]),
    )
    monkeypatch.setattr(views, "get_network_distribution", lambda: pd.DataFrame())
    monkeypatch.setattr(
        views,
        "get_monthly_registrations",
        lambda: pd.DataFrame(
            [{"month": pd.Timestamp("2026-01-01"), "registrations": 2}]
        ),
    )
    monkeypatch.setattr(views, "get_channel_distribution", lambda: pd.DataFrame())

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["monthly"][0]["month"] == "2026-01-01T00:00:00"


def test_dashboard_is_cached_and_fetched_concurrently(monkeypatch):
    monkeypatch.setattr(views, "_dashboard_cache", None)
    monkeypatch.setattr(views, "_dashboard_cache_time", 0.0)
    call_counts = {"metrics": 0}

    def counted_metrics():
        call_counts["metrics"] += 1
        return {"total_accounts": 5}

    monkeypatch.setattr(views, "get_summary_metrics", counted_metrics)
    monkeypatch.setattr(views, "get_status_distribution", lambda: pd.DataFrame())
    monkeypatch.setattr(views, "get_network_distribution", lambda: pd.DataFrame())
    monkeypatch.setattr(views, "get_monthly_registrations", lambda: pd.DataFrame())
    monkeypatch.setattr(views, "get_channel_distribution", lambda: pd.DataFrame())

    first = client.get("/api/dashboard")
    second = client.get("/api/dashboard")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert call_counts["metrics"] == 1


def test_ask_returns_chart_and_table(monkeypatch):
    monkeypatch.setattr(views, "_ask_cache", {})
    result = AgentResult(
        answer="Two accounts.",
        sql="SELECT 2 AS accounts",
        data=pd.DataFrame([{"accounts": 2, "amount": Decimal("4.50")}]),
        chart_type="bar",
        chart_title="Accounts",
        x_column="accounts",
        y_column="amount",
        chart_data=pd.DataFrame([{"accounts": 2, "amount": Decimal("4.50")}]),
        timings={"total": 0.5},
    )
    monkeypatch.setattr(views, "ask_database", lambda question, **kwargs: result)
    monkeypatch.setattr(
        views,
        "run_readonly_query_page",
        lambda sql, **kwargs: (result.data, len(result.data)),
    )

    response = client.post(
        "/api/ask",
        data=json.dumps({"question": "How many accounts?"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["chart"]["type"] == "bar"
    assert response.json()["data"][0]["amount"] == 4.5
    assert response.json()["timings"] == {"total": 0.5}
    assert response.json()["pagination"]["total"] == 1


def test_result_page_returns_requested_page(monkeypatch):
    monkeypatch.setattr(views, "_result_cache", {"abc": (views.time.monotonic(), "SELECT 1")})
    monkeypatch.setattr(
        views,
        "run_readonly_query_page",
        lambda sql, **kwargs: (pd.DataFrame([{"id": 51}]), 120),
    )

    response = client.get("/api/results/abc?page=2&page_size=50")

    assert response.status_code == 200
    assert response.json() == {
        "data": [{"id": 51}],
        "page": 2,
        "page_size": 50,
        "total": 120,
    }


def test_result_download_exports_all_matching_rows(monkeypatch):
    monkeypatch.setattr(views, "_result_cache", {"abc": (views.time.monotonic(), "SELECT 1")})
    monkeypatch.setattr(
        views,
        "run_readonly_query_export",
        lambda sql: pd.DataFrame([{"id": 1}, {"id": 2}]),
    )

    response = client.get("/api/results/abc/download")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert response.content.decode() == "id\r\n1\r\n2\r\n"


def test_ask_serves_repeated_questions_from_cache(monkeypatch):
    monkeypatch.setattr(views, "_ask_cache", {})
    call_count = {"count": 0}
    result = AgentResult(
        answer="Two accounts.",
        sql="SELECT 2 AS accounts",
        data=pd.DataFrame([{"accounts": 2}]),
    )

    def counted_ask_database(question, **kwargs):
        call_count["count"] += 1
        return result

    monkeypatch.setattr(views, "ask_database", counted_ask_database)

    payload = json.dumps({"question": "How many approved members are there?"})
    first = client.post("/api/ask", data=payload, content_type="application/json")
    second = client.post("/api/ask", data=payload, content_type="application/json")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert call_count["count"] == 1


def test_ask_rejects_empty_question():
    response = client.post(
        "/api/ask",
        data=json.dumps({"question": ""}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "question is required"


def test_benefits_returns_contribution_dashboard(monkeypatch):
    monkeypatch.setattr(
        views,
        "get_benefits_summary",
        lambda: {"total_contributions": 10, "total_paid": 250.0},
    )
    monkeypatch.setattr(
        views,
        "get_benefits_status_distribution",
        lambda: pd.DataFrame([{"status": "SUCCESS", "contributions": 8}]),
    )
    monkeypatch.setattr(
        views,
        "get_benefits_vendor_distribution",
        lambda: pd.DataFrame([{"vendor": "MTN", "contributions": 8}]),
    )
    monkeypatch.setattr(
        views,
        "get_monthly_benefits",
        lambda: pd.DataFrame(
            [
                {
                    "month": pd.Timestamp("2026-07-01"),
                    "contributions": 10,
                    "paid_amount": Decimal("250.00"),
                }
            ]
        ),
    )
    monkeypatch.setattr(views, "_benefits_cache", None)

    response = client.get("/api/benefits")

    assert response.status_code == 200
    assert response.json()["vendor"][0]["vendor"] == "MTN"
    assert response.json()["monthly"][0]["paid_amount"] == 250.0
