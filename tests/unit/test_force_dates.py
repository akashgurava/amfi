from __future__ import annotations

from datetime import date

import pytest

from amfi.app import BASE_START_DATE, parse_force_dates


def test_parse_force_year_selector_capped_before_today() -> None:
    today = date(2026, 4, 10)

    selected = parse_force_dates("2026", today=today)

    assert selected[0] == date(2026, 1, 1)
    assert selected[-1] == date(2026, 4, 10)
    assert len(selected) == 100


def test_parse_force_month_selector_capped_before_today() -> None:
    today = date(2026, 2, 10)

    selected = parse_force_dates("2026-02", today=today)

    assert selected == [
        date(2026, 2, 1),
        date(2026, 2, 2),
        date(2026, 2, 3),
        date(2026, 2, 4),
        date(2026, 2, 5),
        date(2026, 2, 6),
        date(2026, 2, 7),
        date(2026, 2, 8),
        date(2026, 2, 9),
        date(2026, 2, 10),
    ]


def test_parse_force_day_selector() -> None:
    today = date(2026, 2, 10)

    selected = parse_force_dates("2026-02-01", today=today)

    assert selected == [date(2026, 2, 1)]


def test_parse_force_mixed_selectors_sorted_and_unique() -> None:
    today = date(2026, 3, 1)

    selected = parse_force_dates("2025,2026-02,2024-01-02,2026-02-01", today=today)

    assert selected[0] == date(2024, 1, 2)
    assert selected[1] == date(2025, 1, 1)
    assert selected[-1] == date(2026, 2, 28)
    assert selected.count(date(2026, 2, 1)) == 1


def test_parse_force_excludes_dates_before_base_start() -> None:
    today = date(2010, 1, 3)

    selected = parse_force_dates("2009,2010-01", today=today)

    assert selected == [BASE_START_DATE, date(2010, 1, 2), date(2010, 1, 3)]


def test_parse_force_future_only_raises() -> None:
    with pytest.raises(ValueError, match="do not include any valid date"):
        parse_force_dates("2026-01-11", today=date(2026, 1, 10))


def test_parse_force_invalid_tokens_raise() -> None:
    with pytest.raises(ValueError, match="Invalid force token"):
        parse_force_dates("2026-1", today=date(2026, 2, 1))

    with pytest.raises(ValueError, match="Invalid date in force token"):
        parse_force_dates("2026-02-30", today=date(2026, 3, 1))

    with pytest.raises(ValueError, match="comma-separated list"):
        parse_force_dates("2026,,2026-01", today=date(2026, 3, 1))
