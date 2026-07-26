"""LLM-powered, read-only natural-language database agent."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import pandas as pd
import requests
from openai import AuthenticationError, OpenAI

from database import get_table_schema, run_readonly_query, table_name
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


def _schema_text() -> str:
    schema = get_table_schema()
    if schema.empty:
        raise ValueError(
            f"Table {table_name()!r} was not found. Check MEMBER_TABLE in .env."
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


def _provider() -> str:
    return os.getenv("LLM_PROVIDER", "openai").strip().lower()


def _openai_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip().strip("\"'")
    if api_key.lower().startswith("api_key="):
        api_key = api_key.split("=", maxsplit=1)[1].strip().strip("\"'")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing from .env.")
    return api_key


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
    if provider == "openai":
        client = OpenAI(api_key=_openai_api_key())
        try:
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
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
        response = requests.post(
            "https://models.github.ai/inference/chat/completions",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {_github_token()}",
                "X-GitHub-Api-Version": "2026-03-10",
            },
            json={
                "model": os.getenv("GITHUB_MODEL", "openai/gpt-4.1-mini"),
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
        client = OpenAI(
            api_key=_groq_api_key(),
            base_url="https://api.groq.com/openai/v1",
        )
        try:
            response = client.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
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
        response = requests.post(
            f"{os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')}/api/chat",
            json={
                "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
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
        "LLM_PROVIDER must be 'groq', 'openai', 'github', or 'ollama'."
    )


def _result_text(data: pd.DataFrame) -> str:
    if data.empty:
        return "No rows returned."
    return data.head(20).to_json(orient="records", date_format="iso")


def ask_database(question: str) -> AgentResult:
    if not question.strip():
        raise ValueError("Enter a question about the database.")

    prompt = SQL_SYSTEM_PROMPT.format(table=table_name(), schema=_schema_text())
    generated = _extract_json(_chat(prompt, question))
    sql = _validate_sql(generated["sql"])
    data = run_readonly_query(sql)

    try:
        answer = _chat(
            ANSWER_SYSTEM_PROMPT,
            f"Question: {question}\nSQL: {sql}\nResult: {_result_text(data)}",
            temperature=0.1,
        ).strip()
    except Exception:
        answer = (
            "No matching records were found."
            if data.empty
            else f"The query returned {len(data):,} result row(s)."
        )

    return AgentResult(answer=answer, sql=sql, data=data)
