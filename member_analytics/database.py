"""PostgreSQL connection and query helpers."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL

load_dotenv()

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_identifier(identifier: str) -> str:
    """Validate and quote a PostgreSQL identifier, including schema-qualified names."""
    parts = identifier.split(".")
    if not parts or any(not _IDENTIFIER.fullmatch(part) for part in parts):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")
    return ".".join(f'"{part}"' for part in parts)


def table_name() -> str:
    return os.getenv("MEMBER_TABLE", "member_accounts")


def column_name(setting: str, default: str) -> str:
    return os.getenv(setting, default)


def _database_url() -> str | URL:
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        if explicit_url.startswith("postgres://"):
            return explicit_url.replace("postgres://", "postgresql+psycopg://", 1)
        if explicit_url.startswith("postgresql://"):
            return explicit_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return explicit_url

    return URL.create(
        drivername="postgresql+psycopg",
        username=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "member_analytics"),
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        _database_url(),
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": 5},
    )


def run_query(
    sql: str,
    params: dict[str, Any] | None = None,
    *,
    max_rows: int | None = None,
) -> pd.DataFrame:
    """Execute a query and return its result as a DataFrame."""
    query = text(sql)
    with get_engine().connect() as connection:
        result = pd.read_sql_query(query, connection, params=params)
    return result.head(max_rows) if max_rows else result


def run_readonly_query(sql: str, *, max_rows: int = 200) -> pd.DataFrame:
    """Execute generated SQL in a read-only transaction with a short timeout."""
    wrapped_sql = f"SELECT * FROM ({sql.rstrip().rstrip(';')}) AS generated_result LIMIT {max_rows}"
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '30s'"))
            result = pd.read_sql_query(text(wrapped_sql), connection)
        finally:
            transaction.rollback()
    return result


def run_readonly_query_page(
    sql: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> tuple[pd.DataFrame, int]:
    """Return one page and the total rows from an already validated SELECT."""
    if page < 1 or page_size < 1 or page_size > 200:
        raise ValueError("Invalid result page or page size.")
    clean_sql = sql.rstrip().rstrip(";")
    count_sql = f"SELECT COUNT(*) AS total FROM ({clean_sql}) AS generated_result"
    page_sql = (
        f"SELECT * FROM ({clean_sql}) AS generated_result "
        f"LIMIT {page_size} OFFSET {(page - 1) * page_size}"
    )
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '30s'"))
            total = int(connection.execute(text(count_sql)).scalar_one())
            frame = pd.read_sql_query(text(page_sql), connection)
        finally:
            transaction.rollback()
    return frame, total


def run_readonly_query_export(sql: str) -> pd.DataFrame:
    """Run an already validated SELECT without the interactive preview cap."""
    clean_sql = sql.rstrip().rstrip(";")
    wrapped_sql = f"SELECT * FROM ({clean_sql}) AS generated_result"
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            result = pd.read_sql_query(text(wrapped_sql), connection)
        finally:
            transaction.rollback()
    return result


def test_connection() -> tuple[bool, str]:
    try:
        result = run_query("SELECT current_database() AS database_name")
        return True, str(result.iloc[0]["database_name"])
    except Exception as exc:
        return False, str(exc)


def get_table_schema(configured_table: str | None = None) -> pd.DataFrame:
    """Return column metadata for the configured member table."""
    configured_table = configured_table or table_name()
    if "." in configured_table:
        schema, table = configured_table.split(".", maxsplit=1)
    else:
        schema, table = "public", configured_table

    return run_query(
        """
        SELECT
            column_name,
            data_type,
            is_nullable
        FROM information_schema.columns
        WHERE table_schema = :schema
          AND table_name = :table
        ORDER BY ordinal_position
        """,
        {"schema": schema, "table": table},
    )
