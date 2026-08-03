"""LLM-powered, read-only natural-language database agent."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import pandas as pd
import requests
from openai import AuthenticationError, AzureOpenAI, OpenAI

from database import get_table_schema, run_readonly_query, table_name
from forecasting import grouped_monthly_forecast, linear_monthly_forecast
from prompts import ANSWER_SYSTEM_PROMPT, SQL_SYSTEM_PROMPT

_BLOCKED_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY|CALL|DO|"
    r"VACUUM|ANALYZE|REFRESH|REINDEX|CLUSTER|COMMENT|SECURITY|PG_SLEEP)\b",
    re.IGNORECASE,
)


@dataclass
class AgentResult:
    answer: str
    sql: str
    data: pd.DataFrame
    analysis_type: str = "query"
    chart_type: str = "none"
    chart_title: str = ""
    x_column: str = ""
    y_column: str = ""
    chart_data: pd.DataFrame | None = None


def _schema_text(configured_table: str | None = None) -> str:
    schema = (
        get_table_schema(configured_table)
        if configured_table
        else get_table_schema()
    )
    if schema.empty:
        raise ValueError(
            f"Table {(configured_table or table_name())!r} was not found. "
            "Check the table configuration in .env."
        )
    return "\n".join(
        f"- {row.column_name}: {row.data_type} (nullable: {row.is_nullable})"
        for row in schema.itertuples()
    )


def _extract_json(content: str) -> dict[str, str]:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("The AI response did not contain valid JSON.")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload.get("sql"), str):
        raise ValueError("The AI response did not contain SQL.")
    return payload


def _projection_periods(
    payload: dict[str, object],
    question: str = "",
) -> int:
    numbered_horizon = re.search(
        r"\bnext\s+(\d+)\s+(month|months|year|years)\b",
        question,
        re.IGNORECASE,
    )
    if numbered_horizon:
        periods = int(numbered_horizon.group(1))
        if numbered_horizon.group(2).lower().startswith("year"):
            periods *= 12
        return min(max(periods, 1), 24)
    if re.search(r"\bnext\s+month\b", question, re.IGNORECASE):
        return 1
    if re.search(r"\bnext\s+year\b", question, re.IGNORECASE):
        return 12
    try:
        periods = int(payload.get("projection_periods", 6))
    except (TypeError, ValueError):
        periods = 6
    return min(max(periods, 1), 24)


def _requests_projection(question: str) -> bool:
    """Return whether the user explicitly requests future estimation."""
    return bool(
        re.search(
            r"\b(forecast|forecasting|project|projected|projection|predict|"
            r"prediction|estimate|estimated|future|expected)\b"
            r"|\bnext\s+\d+\s+(month|months|year|years)\b"
            r"|\bwhat\s+will\b",
            question,
            re.IGNORECASE,
        )
    )


def _requests_grouped_projection(question: str) -> bool:
    return bool(
        re.search(
            r"\b(channel|network|status|product|purpose|category|type)\b",
            question,
            re.IGNORECASE,
        )
    )


def _projection_data(
    data: pd.DataFrame,
    *,
    grouped: bool,
) -> pd.DataFrame | None:
    if not {"period", "value"}.issubset(data.columns):
        return None
    normalized = data.copy()
    if not grouped:
        return normalized
    if "series" in normalized.columns:
        return normalized
    candidates = [
        column for column in normalized.columns if column not in {"period", "value"}
    ]
    if len(candidates) != 1:
        return None
    return normalized.rename(columns={candidates[0]: "series"})


def _projection_window(
    data: pd.DataFrame,
    requested_periods: int,
    *,
    current_date: pd.Timestamp | None = None,
) -> tuple[pd.Timestamp, int]:
    parsed_periods = pd.to_datetime(data["period"], errors="coerce").dropna()
    if parsed_periods.empty:
        raise ValueError("The projection query returned no valid monthly dates.")
    last_historical = parsed_periods.max().to_period("M")
    current_month = (
        current_date if current_date is not None else pd.Timestamp.now()
    ).to_period("M")
    first_target = max(current_month + 1, last_historical + 1)
    bridge_periods = first_target.ordinal - last_historical.ordinal
    calculation_periods = bridge_periods + requested_periods - 1
    if calculation_periods > 120:
        raise ValueError(
            "The historical data is too old to produce a reliable projection "
            "for the requested calendar period."
        )
    return first_target.to_timestamp(), calculation_periods


def _chart_settings(
    payload: dict[str, object],
    data: pd.DataFrame,
) -> tuple[str, str, str, str]:
    chart_type = str(payload.get("chart_type", "none")).lower()
    x_column = str(payload.get("x_column", ""))
    y_column = str(payload.get("y_column", ""))
    title = str(payload.get("chart_title", "Results"))
    paired_charts = {
        "bar",
        "line",
        "pie",
        "donut",
        "area",
        "scatter",
        "funnel",
    }
    if (
        chart_type in paired_charts
        and x_column in data.columns
        and y_column in data.columns
        and len(data) >= 2
    ):
        return chart_type, x_column, y_column, title
    if chart_type == "histogram" and len(data) >= 2:
        value_column = x_column if x_column in data.columns else y_column
        if value_column in data.columns:
            return chart_type, value_column, "", title
    if chart_type == "box" and len(data) >= 2:
        if x_column in data.columns and y_column in data.columns:
            return chart_type, x_column, y_column, title
        value_column = x_column if x_column in data.columns else y_column
        if value_column in data.columns:
            return chart_type, value_column, "", title
    return "none", "", "", ""


def _validate_sql(sql: str) -> str:
    normalized = sql.strip().rstrip(";").strip()
    without_comments = re.sub(r"/\*.*?\*/|--[^\n]*", " ", normalized, flags=re.DOTALL)
    if not re.match(r"^(SELECT|WITH)\b", without_comments, re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")
    if _BLOCKED_SQL.search(without_comments):
        raise ValueError("The generated query contains a blocked SQL operation.")
    if ";" in without_comments:
        raise ValueError("Only one SQL statement is allowed.")
    return normalized


def _is_grouping_error(exc: Exception) -> bool:
    """Return whether a database exception contains PostgreSQL SQLSTATE 42803."""
    current: object | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        sqlstate = getattr(current, "sqlstate", None) or getattr(
            current, "pgcode", None
        )
        if sqlstate == "42803":
            return True
        current = getattr(current, "orig", None)
    return False


def _mentions_identifier(sql: str, identifier: str) -> bool:
    pattern = rf'(?<![A-Za-z0-9_])"?{re.escape(identifier)}"?(?![A-Za-z0-9_])'
    return bool(re.search(pattern, sql, re.IGNORECASE))


def _allows_non_successful_amount(question: str) -> bool:
    return bool(
        re.search(
            r"\b(failed|failure|rejected|pending|attempted|unsuccessful)\b"
            r"|\bby\s+status\b|\beach\s+status\b|\ball\s+statuses\b",
            question,
            re.IGNORECASE,
        )
    )


def _requests_bank_analysis(question: str) -> bool:
    """Return whether the question asks about a bank or banking provider."""
    return bool(re.search(r"\bbank(?:ing|s)?\b", question, re.IGNORECASE))


def _bank_query_is_normalized(sql: str) -> bool:
    """Check that JSON banking details are reduced to a usable bank name."""
    lowered = sql.casefold()
    extracts_bank_name = (
        _mentions_identifier(sql, "banking_details")
        and "bankname" in lowered
        and ("->>" in sql or "jsonb_extract_path_text" in lowered)
    )
    excludes_missing_names = (
        "nullif" in lowered
        and "trim" in lowered
        and "is not null" in lowered
    )
    return extracts_bank_name and excludes_missing_names


def _ensure_bank_query_rules(
    generated: dict[str, str],
    *,
    prompt: str,
    question: str,
) -> dict[str, str]:
    """Repair bank analytics that group the raw JSON document."""
    if not _requests_bank_analysis(question):
        return generated
    sql = _validate_sql(generated["sql"])
    if _bank_query_is_normalized(sql):
        return generated

    repair_request = (
        f"Original user question: {question}\n"
        f"Rejected SQL: {sql}\n"
        "The banking_details column contains JSON serialized as text. Return "
        "the same JSON structure with corrected SQL that extracts the scalar "
        'bank name with banking_details::jsonb ->> \'BankName\', normalizes it '
        "with TRIM, and excludes null and empty bank names before aggregation. "
        "Group and chart the extracted bank-name alias, never the raw JSON "
        "document. Preserve the requested ranking and limit."
    )
    repaired = _extract_json(_chat(prompt, repair_request))
    repaired_sql = _validate_sql(repaired["sql"])
    if not _bank_query_is_normalized(repaired_sql):
        raise ValueError(
            "The generated bank query did not extract and filter valid bank names."
        )
    return repaired


def _contains_numeric_literal(sql: str, expected: str) -> bool:
    try:
        expected_value = Decimal(expected)
    except InvalidOperation:
        return False
    tokens = re.findall(
        r"(?<![A-Za-z0-9_.])(?:[0-9]+(?:[.][0-9]*)?|[.][0-9]+)"
        r"(?:[eE][+-]?[0-9]+)?(?![A-Za-z0-9_.])",
        sql,
    )
    for token in tokens:
        try:
            if Decimal(token) == expected_value:
                return True
        except InvalidOperation:
            continue
    return False


def _ensure_monetary_query_rules(
    generated: dict[str, str],
    *,
    prompt: str,
    question: str,
) -> dict[str, str]:
    sql = _validate_sql(generated["sql"])
    monetary_columns = [
        column.strip()
        for column in os.getenv(
            "MONETARY_COLUMNS",
            "amount,target_amount",
        ).split(",")
        if column.strip()
    ]
    status_column = os.getenv("STATUS_COLUMN", "status")
    approved_value = os.getenv("APPROVED_VALUE", "approved")
    target_column = os.getenv("TARGET_AMOUNT_COLUMN", "target_amount")
    max_target = os.getenv("MAX_TARGET_AMOUNT", "10000000000")
    used_columns = [
        column for column in monetary_columns if _mentions_identifier(sql, column)
    ]
    if not used_columns:
        return generated
    requires_success = not _allows_non_successful_amount(question)
    success_filter_ok = not requires_success or (
        _mentions_identifier(sql, status_column)
        and approved_value.casefold() in sql.casefold()
    )
    uses_target = target_column in used_columns
    target_limit_ok = not uses_target or _contains_numeric_literal(sql, max_target)
    target_parse_ok = not uses_target or (
        "~" in sql or "regexp_replace" in sql.casefold()
    )
    if success_filter_ok and target_limit_ok and target_parse_ok:
        return generated

    missing_rules = []
    if not success_filter_ok:
        missing_rules.append(
            f"filter rows to successful status {approved_value!r}"
        )
    if not target_parse_ok:
        missing_rules.append(
            f"safely validate text in {target_column!r} before casting it"
        )
    if not target_limit_ok:
        missing_rules.append(
            f"restrict parsed {target_column!r} values to 0 through {max_target}"
        )
    repair_request = (
        f"Original user question: {question}\n"
        f"Rejected SQL: {sql}\n"
        "The monetary query violates required business or data-quality rules: "
        f"{'; '.join(missing_rules)}. Return the same JSON structure with "
        "corrected SQL. Apply every rule before aggregation, charting, or "
        "projection."
    )
    repaired = _extract_json(_chat(prompt, repair_request))
    repaired_sql = _validate_sql(repaired["sql"])
    repaired_success_ok = not requires_success or (
        _mentions_identifier(repaired_sql, status_column)
        and approved_value.casefold() in repaired_sql.casefold()
    )
    repaired_target_ok = not uses_target or (
        _contains_numeric_literal(repaired_sql, max_target)
        and ("~" in repaired_sql or "regexp_replace" in repaired_sql.casefold())
    )
    if not repaired_success_ok or not repaired_target_ok:
        raise ValueError(
            "The generated monetary query did not satisfy the required status "
            "and data-quality rules."
        )
    return repaired


def _run_generated_query(
    generated: dict[str, str],
    *,
    prompt: str,
    question: str,
) -> tuple[dict[str, str], str, pd.DataFrame]:
    generated = _ensure_bank_query_rules(
        generated,
        prompt=prompt,
        question=question,
    )
    generated = _ensure_monetary_query_rules(
        generated,
        prompt=prompt,
        question=question,
    )
    sql = _validate_sql(generated["sql"])
    try:
        return generated, sql, run_readonly_query(sql)
    except Exception as exc:
        if not _is_grouping_error(exc):
            raise

    repair_request = (
        f"Original user question: {question}\n"
        f"Rejected SQL: {sql}\n"
        "PostgreSQL rejected the GROUP BY clause with SQLSTATE 42803. "
        "Return the same JSON structure with corrected SQL. Group derived "
        "SELECT expressions by ordinal position (for example GROUP BY 1) or "
        "repeat the full expression; do not group by an output alias."
    )
    repaired = _extract_json(_chat(prompt, repair_request))
    repaired = _ensure_monetary_query_rules(
        repaired,
        prompt=prompt,
        question=question,
    )
    repaired_sql = _validate_sql(repaired["sql"])
    return repaired, repaired_sql, run_readonly_query(repaired_sql)


def _provider() -> str:
    return os.getenv("LLM_PROVIDER", "openai").strip().lower()


def _openai_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip().strip("\"'")
    if api_key.lower().startswith("api_key="):
        api_key = api_key.split("=", maxsplit=1)[1].strip().strip("\"'")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing from .env.")
    return api_key


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip().strip("\"'")
    if not value:
        raise ValueError(f"{name} is missing from .env.")
    return value


def _azure_chat_deployment() -> str:
    deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip().strip("\"'")
    if not deployment:
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip().strip("\"'")
    if not deployment:
        raise ValueError(
            "AZURE_OPENAI_CHAT_DEPLOYMENT or AZURE_OPENAI_DEPLOYMENT is missing "
            "from .env."
        )
    return deployment


def _github_token() -> str:
    token = os.getenv("GITHUB_TOKEN", "").strip().strip("\"'")
    if not token:
        token = _openai_api_key()
    return token


def _groq_api_key() -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip().strip("\"'")
    if api_key.lower().startswith("api_key="):
        api_key = api_key.split("=", maxsplit=1)[1].strip().strip("\"'")
    if not api_key:
        raise ValueError("GROQ_API_KEY is missing from .env.")
    return api_key


def _chat(system_prompt: str, user_prompt: str, *, temperature: float = 0) -> str:
    provider = _provider()
    if provider == "azure":
        model = _azure_chat_deployment()
        client = AzureOpenAI(
            azure_endpoint=_required_env("AZURE_OPENAI_ENDPOINT"),
            api_key=_required_env("AZURE_OPENAI_API_KEY"),
            api_version=_required_env("AZURE_OPENAI_API_VERSION"),
        )
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except AuthenticationError as exc:
            raise ValueError(
                "Azure OpenAI rejected the API key. Check the Azure endpoint, "
                "API key, API version, and chat deployment, then restart Streamlit."
            ) from exc
        return response.choices[0].message.content or ""

    if provider == "openai":
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        client = OpenAI(api_key=_openai_api_key())
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except AuthenticationError as exc:
            raise ValueError(
                "OpenAI rejected the API key. Use a valid OpenAI Platform key in "
                "OPENAI_API_KEY, then restart Streamlit."
            ) from exc
        return response.choices[0].message.content or ""

    if provider == "github":
        model = os.getenv("GITHUB_MODEL", "openai/gpt-4.1-mini")
        response = requests.post(
            "https://models.github.ai/inference/chat/completions",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {_github_token()}",
                "X-GitHub-Api-Version": "2026-03-10",
            },
            json={
                "model": model,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=60,
        )
        if response.status_code in {401, 403}:
            raise ValueError(
                "GitHub Models rejected the token. Use a fine-grained GitHub PAT "
                "with the 'models: read' permission, then restart Streamlit."
            )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"])

    if provider == "groq":
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        client = OpenAI(
            api_key=_groq_api_key(),
            base_url="https://api.groq.com/openai/v1",
        )
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except AuthenticationError as exc:
            raise ValueError(
                "Groq rejected the API key. Create a key in GroqCloud, paste it "
                "into GROQ_API_KEY, and restart Streamlit."
            ) from exc
        return response.choices[0].message.content or ""

    if provider == "ollama":
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        response = requests.post(
            f"{os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')}/api/chat",
            json={
                "model": model,
                "stream": False,
                "options": {"temperature": temperature},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=60,
        )
        response.raise_for_status()
        return str(response.json()["message"]["content"])

    raise ValueError(
        "LLM_PROVIDER must be 'azure', 'groq', 'openai', 'github', or 'ollama'."
    )


def _result_text(data: pd.DataFrame) -> str:
    if data.empty:
        return "No rows returned."
    return data.head(20).to_json(orient="records", date_format="iso")


def ask_database(question: str, *, target_table: str | None = None) -> AgentResult:
    if not question.strip():
        raise ValueError("Enter a question about the database.")

    configured_table = target_table or table_name()
    schema_text = _schema_text(target_table)
    if configured_table.lower().endswith("smartlife_contributions"):
        schema_text += (
            "\n\nBenefits data rules:"
            "\n- member_name = 'Suspense' is a pooled/system placeholder, not an "
            "individual contributor. Exclude it from top/highest contributor or "
            "member rankings."
            "\n- Identify an individual contributor by nssf_number. For a named "
            "ranking, group by nssf_number and use MAX(member_name) as the display "
            "name; do not group unrelated contributors only by member_name."
            "\n- Distinguish transaction from contributor questions: 'highest "
            "contribution' or 'largest contribution' means the single largest "
            "successful paid_amount row; 'highest contributor', 'top contributor', "
            "or 'highest total contribution by member' means SUM(paid_amount) "
            "grouped by nssf_number."
            "\n- If the user asks for the highest/top contributor AND 'their "
            "contributions', first find the top nssf_number by total successful "
            "paid_amount in a CTE, then return every SUCCESS transaction for that "
            "nssf_number as separate rows. Include nssf_number, member_name, "
            "record_date, partner_id, vendor, approved_date, paid_amount, and the "
            "contributor's total as a window value. Do not return only one "
            "aggregated row."
            "\n- Treat paid_amount as the contribution amount and, unless the user "
            "asks otherwise, include only status = 'SUCCESS' when totaling paid "
            "contributions."
        )
    prompt = SQL_SYSTEM_PROMPT.format(
        table=configured_table,
        schema=schema_text,
        approved_value=os.getenv("APPROVED_VALUE", "approved"),
        pending_value=os.getenv("PENDING_VALUE", "pending"),
        rejected_value=os.getenv("REJECTED_VALUE", "rejected"),
        monetary_columns=os.getenv("MONETARY_COLUMNS", "amount,target_amount"),
        target_amount_column=os.getenv(
            "TARGET_AMOUNT_COLUMN",
            "target_amount",
        ),
        max_target_amount=os.getenv("MAX_TARGET_AMOUNT", "10000000000"),
    )
    generated = _extract_json(_chat(prompt, question))
    generated, sql, data = _run_generated_query(
        generated,
        prompt=prompt,
        question=question,
    )
    requested_analysis = str(generated.get("analysis_type", "query")).lower()
    analysis_type = (
        "projection"
        if requested_analysis == "projection" and _requests_projection(question)
        else "query"
    )

    if analysis_type == "projection":
        grouped_projection = _requests_grouped_projection(question)
        normalized_data = _projection_data(data, grouped=grouped_projection)
        if normalized_data is None:
            required_columns = (
                '"period", "series", and "value"'
                if grouped_projection
                else '"period" and "value"'
            )
            repair_request = (
                f"Original user question: {question}\n"
                f"Rejected SQL: {sql}\n"
                "The projection SQL returned the wrong result shape. Return "
                "the same JSON structure with corrected historical monthly SQL "
                f"whose exact result aliases are {required_columns}. "
                'Alias the category as "series" for a grouped comparison. '
                "Do not calculate future rows in SQL."
            )
            repaired = _extract_json(_chat(prompt, repair_request))
            generated, sql, data = _run_generated_query(
                repaired,
                prompt=prompt,
                question=question,
            )
            normalized_data = _projection_data(
                data,
                grouped=grouped_projection,
            )
            if normalized_data is None:
                raise ValueError(
                    "The projection query must return historical monthly "
                    f"columns {required_columns}."
                )

        requested_periods = _projection_periods(generated, question)
        first_target, calculation_periods = _projection_window(
            normalized_data,
            requested_periods,
        )
        if grouped_projection:
            projection = grouped_monthly_forecast(
                normalized_data,
                date_column="period",
                series_column="series",
                value_column="value",
                periods=calculation_periods,
            )
        else:
            projection = linear_monthly_forecast(
                normalized_data,
                date_column="period",
                value_column="value",
                periods=calculation_periods,
            )
        answer_data = projection.forecast[
            projection.forecast["period"] >= first_target
        ].copy()
        chart_title = str(generated.get("chart_title", "Trend projection"))
        answer_context = (
            f"Analysis type: projection\n"
            f"Question: {question}\n"
            f"Method: Linear trend fitted independently to up to 24 recent "
            f"complete monthly values"
            f"{' for each series' if grouped_projection else ''}.\n"
            f"Projection: {_result_text(answer_data)}"
        )
        try:
            answer = _chat(
                ANSWER_SYSTEM_PROMPT,
                answer_context,
                temperature=0.1,
            ).strip()
        except Exception:
            if grouped_projection:
                final_period = answer_data["period"].max()
                winner = (
                    answer_data[answer_data["period"] == final_period]
                    .sort_values("projected_value", ascending=False)
                    .iloc[0]
                )
                answer = (
                    f"{winner['series']} is expected to have the most "
                    f"enrollments in {final_period.strftime('%B %Y')}, with a "
                    f"trend-based estimate of "
                    f"{winner['projected_value']:,.0f}."
                )
            else:
                final_row = answer_data.iloc[-1]
                answer = (
                    f"The trend-based estimate for "
                    f"{final_row['period'].strftime('%B %Y')} is "
                    f"{final_row['projected_value']:,.0f}."
                )
        return AgentResult(
            answer=answer,
            sql=sql,
            data=answer_data,
            analysis_type="projection",
            chart_type="line",
            chart_title=chart_title,
            x_column="period",
            y_column="projected_value",
            chart_data=projection.chart_data,
        )

    try:
        answer = _chat(
            ANSWER_SYSTEM_PROMPT,
            f"Analysis type: query\n"
            f"Question: {question}\n"
            f"SQL: {sql}\n"
            f"Result: {_result_text(data)}",
            temperature=0.1,
        ).strip()
    except Exception:
        answer = (
            "No matching records were found."
            if data.empty
            else f"The query returned {len(data):,} result row(s)."
        )

    chart_type, x_column, y_column, chart_title = _chart_settings(generated, data)
    return AgentResult(
        answer=answer,
        sql=sql,
        data=data,
        chart_type=chart_type,
        chart_title=chart_title,
        x_column=x_column,
        y_column=y_column,
        chart_data=data if chart_type != "none" else None,
    )
