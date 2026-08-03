"""FastAPI entry point for the Natural Language Analytics System."""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import ask_database
from analytics import (
    get_benefits_status_distribution,
    get_benefits_summary,
    get_benefits_vendor_distribution,
    get_channel_distribution,
    get_monthly_benefits,
    get_monthly_registrations,
    get_network_distribution,
    get_status_distribution,
    get_summary_metrics,
)
from database import test_connection


DEMO_QUESTIONS = [
    "How many approved members are there?",
    "Which network has the highest number of members?",
    "How many records were created this month?",
    "Show members by channel.",
    "What is the total amount collected?",
    "How many pending applications exist?",
    "Which status has the highest count?",
    "Show the top ten product codes.",
    "Project monthly registrations for the next 6 months.",
    "Forecast the total monthly amount for the next year.",
]


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    domain: Literal["enrolments", "benefits"] = "enrolments"


def _json_value(value: Any) -> Any:
    """Convert pandas, NumPy, date, and decimal values to JSON-safe values."""
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "item"):
        return value.item()
    return value


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None:
        return []
    return [
        {str(column): _json_value(value) for column, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


app = FastAPI(
    title="Member Analytics API",
    version="1.0.0",
    description="Read-only analytics and natural-language database API.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_benefits_cache: dict[str, Any] | None = None
_benefits_cache_time = 0.0
_benefits_cache_lock = threading.Lock()


@app.get("/api/health")
def health() -> dict[str, Any]:
    connected, detail = test_connection()
    return {"status": "ok" if connected else "degraded", "database": connected, "detail": detail}


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    try:
        return {
            "metrics": get_summary_metrics(),
            "status": _records(get_status_distribution()),
            "network": _records(get_network_distribution()),
            "monthly": _records(get_monthly_registrations()),
            "channel": _records(get_channel_distribution()),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not load dashboard data: {exc}") from exc


@app.get("/api/benefits")
def benefits() -> dict[str, Any]:
    global _benefits_cache, _benefits_cache_time
    cache_ttl = int(os.getenv("DASHBOARD_CACHE_TTL", "60"))
    now = time.monotonic()
    if _benefits_cache is not None and now - _benefits_cache_time < cache_ttl:
        return _benefits_cache
    try:
        # The lock makes simultaneous browser requests share one database load.
        with _benefits_cache_lock:
            now = time.monotonic()
            if (
                _benefits_cache is not None
                and now - _benefits_cache_time < cache_ttl
            ):
                return _benefits_cache
            # These aggregates are independent. Running them concurrently cuts
            # cold-load latency on the larger contributions table.
            with ThreadPoolExecutor(max_workers=4) as executor:
                metrics_future = executor.submit(get_benefits_summary)
                status_future = executor.submit(get_benefits_status_distribution)
                vendor_future = executor.submit(get_benefits_vendor_distribution)
                monthly_future = executor.submit(get_monthly_benefits)
                payload = {
                    "metrics": metrics_future.result(),
                    "status": _records(status_future.result()),
                    "vendor": _records(vendor_future.result()),
                    "monthly": _records(monthly_future.result()),
                }
            _benefits_cache = payload
            _benefits_cache_time = time.monotonic()
            return payload
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not load benefits data: {exc}",
        ) from exc


BENEFITS_QUESTIONS = [
    "Who is the highest contributor and what are their contributions?",
    "What is the total amount paid successfully?",
    "How many contributions are pending?",
    "Show contributions by vendor.",
    "How many unique members have contributed?",
    "Show monthly successful contribution amounts.",
    "Which vendor processed the most contributions?",
]


@app.get("/api/questions")
def questions(domain: Literal["enrolments", "benefits"] = "enrolments") -> dict[str, list[str]]:
    return {"questions": BENEFITS_QUESTIONS if domain == "benefits" else DEMO_QUESTIONS}


@app.post("/api/ask")
def ask(request: QuestionRequest) -> dict[str, Any]:
    try:
        target_table = (
            os.getenv("BENEFITS_TABLE", "public.smartlife_contributions")
            if request.domain == "benefits"
            else None
        )
        result = ask_database(request.question.strip(), target_table=target_table)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not answer the question: {exc}") from exc

    return {
        "answer": result.answer,
        "sql": result.sql,
        "analysis_type": result.analysis_type,
        "chart": {
            "type": result.chart_type,
            "title": result.chart_title,
            "x_column": result.x_column,
            "y_column": result.y_column,
            "data": _records(result.chart_data),
        },
        "data": _records(result.data),
    }
