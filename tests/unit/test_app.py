from __future__ import annotations

from datetime import date, timedelta

import duckdb

from amfi.app import (
    BASE_START_DATE,
    get_dates_to_fetch,
    is_invalid_response_error,
    is_rate_limit_error,
)
from amfi.etl import create_bronze_table


def test_is_rate_limit_error_patterns() -> None:
    assert is_rate_limit_error("HTTP 429 Too Many Requests") is True
    assert is_rate_limit_error("rate limit exceeded") is True
    assert is_rate_limit_error("network timeout") is False


def test_is_invalid_response_error_patterns() -> None:
    assert is_invalid_response_error("Invalid JSON for 2026-01-01") is True
    assert is_invalid_response_error("Unexpected response type") is True
    assert is_invalid_response_error("HTTP 503 service unavailable") is False


def test_get_dates_to_fetch_fetch_all() -> None:
    conn = duckdb.connect(":memory:")
    try:
        result = get_dates_to_fetch(conn, fetch_all=True)
        assert result
        assert result[0] == BASE_START_DATE
        assert result[-1] == date.today()
    finally:
        conn.close()


def test_get_dates_to_fetch_fetch_new_from_base_when_empty() -> None:
    conn = duckdb.connect(":memory:")
    try:
        result = get_dates_to_fetch(conn, fetch_all=False)
        assert result
        assert result[0] == BASE_START_DATE
        assert result[-1] == date.today()
    finally:
        conn.close()


def test_get_dates_to_fetch_fetch_new_returns_missing_dates() -> None:
    conn = duckdb.connect(":memory:")
    try:
        create_bronze_table(conn)
        conn.execute(
            "INSERT INTO raw_nav (hnav_date, _source_file) VALUES (?, ?)",
            ["2020-01-10T00:00:00.000Z", "test"],
        )
        conn.execute(
            "INSERT INTO raw_nav (hnav_date, _source_file) VALUES (?, ?)",
            ["2020-01-12T00:00:00.000Z", "test"],
        )

        result = get_dates_to_fetch(conn, fetch_all=False)
        assert date(2020, 1, 10) not in result
        assert date(2020, 1, 12) not in result
        assert date(2020, 1, 11) in result
    finally:
        conn.close()


def test_get_dates_to_fetch_excludes_future_dates() -> None:
    conn = duckdb.connect(":memory:")
    try:
        create_bronze_table(conn)
        tomorrow = date.today() + timedelta(days=1)
        conn.execute(
            "INSERT INTO raw_nav (hnav_date, _source_file) VALUES (?, ?)",
            [f"{tomorrow.isoformat()}T00:00:00.000Z", "test"],
        )

        result = get_dates_to_fetch(conn, fetch_all=False)
        assert tomorrow not in result
        assert result
    finally:
        conn.close()
