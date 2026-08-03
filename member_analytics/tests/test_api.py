from decimal import Decimal

import pandas as pd
from fastapi.testclient import TestClient

import api
from agent import AgentResult


client = TestClient(api.app)


def test_dashboard_serializes_dataframes(monkeypatch):
    monkeypatch.setattr(api, "get_summary_metrics", lambda: {"total_accounts": 2})
    monkeypatch.setattr(api, "get_status_distribution", lambda: pd.DataFrame([{"status": "approved", "accounts": 2}]))
    monkeypatch.setattr(api, "get_network_distribution", lambda: pd.DataFrame())
    monkeypatch.setattr(api, "get_monthly_registrations", lambda: pd.DataFrame([{"month": pd.Timestamp("2026-01-01"), "registrations": 2}]))
    monkeypatch.setattr(api, "get_channel_distribution", lambda: pd.DataFrame())

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["monthly"][0]["month"] == "2026-01-01T00:00:00"


def test_ask_returns_chart_and_table(monkeypatch):
    result = AgentResult(
        answer="Two accounts.",
        sql="SELECT 2 AS accounts",
        data=pd.DataFrame([{"accounts": 2, "amount": Decimal("4.50")}]),
        chart_type="bar",
        chart_title="Accounts",
        x_column="accounts",
        y_column="amount",
        chart_data=pd.DataFrame([{"accounts": 2, "amount": Decimal("4.50")}]),
    )
    monkeypatch.setattr(api, "ask_database", lambda question, **kwargs: result)

    response = client.post("/api/ask", json={"question": "How many?"})

    assert response.status_code == 200
    assert response.json()["chart"]["type"] == "bar"
    assert response.json()["data"][0]["amount"] == 4.5


def test_ask_rejects_empty_question():
    response = client.post("/api/ask", json={"question": ""})
    assert response.status_code == 422


def test_benefits_returns_contribution_dashboard(monkeypatch):
    monkeypatch.setattr(
        api,
        "get_benefits_summary",
        lambda: {"total_contributions": 10, "total_paid": 250.0},
    )
    monkeypatch.setattr(
        api,
        "get_benefits_status_distribution",
        lambda: pd.DataFrame([{"status": "SUCCESS", "contributions": 8}]),
    )
    monkeypatch.setattr(
        api,
        "get_benefits_vendor_distribution",
        lambda: pd.DataFrame([{"vendor": "MTN", "contributions": 8}]),
    )
    monkeypatch.setattr(
        api,
        "get_monthly_benefits",
        lambda: pd.DataFrame(
            [{"month": pd.Timestamp("2026-07-01"), "contributions": 10, "paid_amount": Decimal("250.00")}]
        ),
    )

    response = client.get("/api/benefits")

    assert response.status_code == 200
    assert response.json()["vendor"][0]["vendor"] == "MTN"
    assert response.json()["monthly"][0]["paid_amount"] == 250.0
