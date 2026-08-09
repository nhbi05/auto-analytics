"""Django views preserving the existing frontend API contract."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

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
from database import run_readonly_query_export, run_readonly_query_page, test_connection


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

BENEFITS_QUESTIONS = [
    "Who is the highest contributor and what are their contributions?",
    "What is the total amount paid successfully?",
    "How many contributions are pending?",
    "Show contributions by vendor.",
    "How many unique members have contributed?",
    "Show monthly successful contribution amounts.",
    "Which vendor processed the most contributions?",
]


def _json_value(value: Any) -> Any:
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


def _error(detail: str, status: int) -> JsonResponse:
    return JsonResponse({"detail": detail}, status=status)


_benefits_cache: dict[str, Any] | None = None
_benefits_cache_time = 0.0
_benefits_cache_lock = threading.Lock()

_dashboard_cache: dict[str, Any] | None = None
_dashboard_cache_time = 0.0
_dashboard_cache_lock = threading.Lock()

_ask_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
_ask_cache_lock = threading.Lock()
_ASK_CACHE_MAX_ENTRIES = 64

_result_cache: dict[str, tuple[float, str]] = {}
_result_cache_lock = threading.Lock()
_RESULT_CACHE_TTL = 1800
_RESULT_PAGE_SIZE = 50


def _store_result(sql: str) -> str:
    result_id = uuid.uuid4().hex
    now = time.monotonic()
    with _result_cache_lock:
        expired = [
            key for key, (created, _) in _result_cache.items()
            if now - created >= _RESULT_CACHE_TTL
        ]
        for key in expired:
            _result_cache.pop(key, None)
        _result_cache[result_id] = (now, sql)
    return result_id


def _result_sql(result_id: str) -> str | None:
    with _result_cache_lock:
        stored = _result_cache.get(result_id)
    if stored is None or time.monotonic() - stored[0] >= _RESULT_CACHE_TTL:
        return None
    return stored[1]


@require_GET
def result_page(request: HttpRequest, result_id: str) -> JsonResponse:
    sql = _result_sql(result_id)
    if sql is None:
        return _error("This result has expired. Ask the question again.", 404)
    try:
        page = int(request.GET.get("page", "1"))
        page_size = int(request.GET.get("page_size", str(_RESULT_PAGE_SIZE)))
        frame, total = run_readonly_query_page(sql, page=page, page_size=page_size)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:
        return _error(f"Could not load the result page: {exc}", 503)
    return JsonResponse(
        {"data": _records(frame), "page": page, "page_size": page_size, "total": total}
    )


@require_GET
def result_download(_request: HttpRequest, result_id: str) -> HttpResponse:
    sql = _result_sql(result_id)
    if sql is None:
        return _error("This result has expired. Ask the question again.", 404)
    try:
        frame = run_readonly_query_export(sql)
    except Exception as exc:
        return _error(f"Could not export the results: {exc}", 503)
    response = HttpResponse(frame.to_csv(index=False), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="query-results-{result_id[:8]}.csv"'
    return response


@require_GET
def health(_request: HttpRequest) -> JsonResponse:
    connected, detail = test_connection()
    return JsonResponse(
        {"status": "ok" if connected else "degraded", "database": connected, "detail": detail}
    )


@require_GET
def dashboard(_request: HttpRequest) -> JsonResponse:
    global _dashboard_cache, _dashboard_cache_time
    cache_ttl = int(os.getenv("DASHBOARD_CACHE_TTL", "60"))
    now = time.monotonic()
    if _dashboard_cache is not None and now - _dashboard_cache_time < cache_ttl:
        return JsonResponse(_dashboard_cache)
    try:
        with _dashboard_cache_lock:
            now = time.monotonic()
            if _dashboard_cache is None or now - _dashboard_cache_time >= cache_ttl:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    metrics_future = executor.submit(get_summary_metrics)
                    status_future = executor.submit(get_status_distribution)
                    network_future = executor.submit(get_network_distribution)
                    monthly_future = executor.submit(get_monthly_registrations)
                    channel_future = executor.submit(get_channel_distribution)
                    _dashboard_cache = {
                        "metrics": metrics_future.result(),
                        "status": _records(status_future.result()),
                        "network": _records(network_future.result()),
                        "monthly": _records(monthly_future.result()),
                        "channel": _records(channel_future.result()),
                    }
                _dashboard_cache_time = time.monotonic()
            return JsonResponse(_dashboard_cache)
    except Exception as exc:
        return _error(f"Could not load dashboard data: {exc}", 503)


@require_GET
def benefits(_request: HttpRequest) -> JsonResponse:
    global _benefits_cache, _benefits_cache_time
    cache_ttl = int(os.getenv("DASHBOARD_CACHE_TTL", "60"))
    now = time.monotonic()
    if _benefits_cache is not None and now - _benefits_cache_time < cache_ttl:
        return JsonResponse(_benefits_cache)
    try:
        with _benefits_cache_lock:
            now = time.monotonic()
            if _benefits_cache is None or now - _benefits_cache_time >= cache_ttl:
                with ThreadPoolExecutor(max_workers=4) as executor:
                    metrics_future = executor.submit(get_benefits_summary)
                    status_future = executor.submit(get_benefits_status_distribution)
                    vendor_future = executor.submit(get_benefits_vendor_distribution)
                    monthly_future = executor.submit(get_monthly_benefits)
                    _benefits_cache = {
                        "metrics": metrics_future.result(),
                        "status": _records(status_future.result()),
                        "vendor": _records(vendor_future.result()),
                        "monthly": _records(monthly_future.result()),
                    }
                _benefits_cache_time = time.monotonic()
            return JsonResponse(_benefits_cache)
    except Exception as exc:
        return _error(f"Could not load benefits data: {exc}", 503)


@require_GET
def questions(request: HttpRequest) -> JsonResponse:
    domain = request.GET.get("domain", "enrolments")
    if domain not in {"enrolments", "benefits"}:
        return _error("domain must be either enrolments or benefits", 400)
    return JsonResponse(
        {"questions": BENEFITS_QUESTIONS if domain == "benefits" else DEMO_QUESTIONS}
    )


@csrf_exempt
@require_POST
def ask(request: HttpRequest) -> JsonResponse:
    try:
        body = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error("Request body must be valid JSON.", 400)
    question = body.get("question")
    domain = body.get("domain", "enrolments")
    if not isinstance(question, str) or not question.strip():
        return _error("question is required", 400)
    if len(question) > 1000:
        return _error("question must not exceed 1000 characters", 400)
    if domain not in {"enrolments", "benefits"}:
        return _error("domain must be either enrolments or benefits", 400)

    question = question.strip()
    target_table = (
        os.getenv("BENEFITS_TABLE", "public.smartlife_contributions")
        if domain == "benefits"
        else None
    )
    cache_ttl = int(os.getenv("ASK_CACHE_TTL", "120"))
    cache_key = (question.lower(), domain, target_table or "")
    if cache_ttl > 0:
        with _ask_cache_lock:
            cached = _ask_cache.get(cache_key)
        if cached is not None and time.monotonic() - cached[0] < cache_ttl:
            return JsonResponse(cached[1])

    try:
        result = ask_database(question, target_table=target_table)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception as exc:
        return _error(f"Could not answer the question: {exc}", 503)

    payload = {
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
    if result.analysis_type != "projection":
        result_id = _store_result(result.sql)
        try:
            page_data, total = run_readonly_query_page(
                result.sql,
                page=1,
                page_size=_RESULT_PAGE_SIZE,
            )
            payload["data"] = _records(page_data)
            payload["pagination"] = {
                "result_id": result_id,
                "page": 1,
                "page_size": _RESULT_PAGE_SIZE,
                "total": total,
            }
        except Exception:
            payload["pagination"] = {
                "result_id": result_id,
                "page": 1,
                "page_size": len(payload["data"]),
                "total": len(payload["data"]),
            }
    if result.timings:
        payload["timings"] = result.timings

    if cache_ttl > 0:
        with _ask_cache_lock:
            _ask_cache[cache_key] = (time.monotonic(), payload)
            if len(_ask_cache) > _ASK_CACHE_MAX_ENTRIES:
                oldest_key = min(_ask_cache, key=lambda key: _ask_cache[key][0])
                _ask_cache.pop(oldest_key, None)
    return JsonResponse(payload)


def frontend(_request: HttpRequest) -> HttpResponse:
    index_file = Path(settings.BASE_DIR) / "frontend" / "dist" / "index.html"
    if not index_file.exists():
        return HttpResponse(
            "React build not found. Run npm run build in the frontend directory.",
            status=503,
            content_type="text/plain",
        )
    return HttpResponse(index_file.read_text(encoding="utf-8"), content_type="text/html")
