"""Unit tests for :mod:`amfi.metrics`."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from amfi.data import RawNavResponse
from amfi.db import Database
from amfi.metrics import (
    DatabaseMetricsAdapter,
    MetricsBuilder,
    MetricsConfig,
    all_periods,
    period_order,
)


def _nav_row(sd_id: str, d: date, amt: float) -> RawNavResponse:
    return RawNavResponse.from_dict(
        {
            "SD_ID": sd_id,
            "NAV_Name": "Plan",
            "hNAV_Amt": f"{amt}",
            "ISIN_RI": "",
            "ISIN_PO": "",
            "hNAV_Date": d.isoformat(),
            "hNAV_Dtstamp": f"{d.isoformat()}T00:00:00Z",
            "hNAV_reissue": "",
            "hNAV_repurchase": "",
            "hNAV_Upload_display": "01 Jan 2024 00:00:00",
        }
    )


def _seed_minimal_plans(db: Database, sd_ids: list[int]) -> None:
    """Write a synthetic ``plans`` table with the columns referenced by
    :class:`MetricsBuilder`'s data load and the per-period views
    (``sd_id, scheme, aum``)."""
    # DuckDB refuses DROP VIEW on a table and vice-versa; inspect first.
    row = db.conn.execute(
        "SELECT table_type FROM information_schema.tables WHERE table_name = 'plans'"
    ).fetchone()
    if row:
        existing_kind = "VIEW" if row[0] == "VIEW" else "TABLE"
        db.conn.execute(f"DROP {existing_kind} IF EXISTS plans")
    db.conn.execute("CREATE TABLE plans (sd_id INTEGER, scheme VARCHAR, aum DOUBLE)")
    db.conn.executemany(
        "INSERT INTO plans VALUES (?, ?, ?)",
        [(sd, f"Fund {sd}", 100.0) for sd in sd_ids],
    )


def _seed_nav_table(db: Database, rows: list[tuple[int, date, float]]) -> None:
    """Write a synthetic ``nav`` table (sd_id, date, nav, raw_nav).

    ``nav`` is normally a UNION view over ``nav_funds`` + ``nav_portfolios``;
    these tests substitute it with a standalone table so they can seed rows
    directly. Drop the view first, then build the table.
    """
    # ``nav`` may be a VIEW (fresh init) or a TABLE (second call in the same
    # test); inspect first because DuckDB refuses DROP VIEW on a table and
    # vice versa.
    row = db.conn.execute(
        "SELECT table_type FROM information_schema.tables WHERE table_name = 'nav'"
    ).fetchone()
    if row:
        kind = "VIEW" if row[0] == "VIEW" else "TABLE"
        db.conn.execute(f"DROP {kind} IF EXISTS nav")
    db.conn.execute(
        "CREATE TABLE nav (sd_id INTEGER, date DATE, nav DOUBLE, raw_nav DOUBLE)"
    )
    db.conn.executemany(
        "INSERT INTO nav VALUES (?, ?, ?, ?)",
        [(sd, d, v, v) for sd, d, v in rows],
    )


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database(db_path=str(tmp_path / "m.duckdb"))
    d.create_database_objects()
    yield d
    d.close()


# ---------------------------------------------------------------------------
# Period keys
# ---------------------------------------------------------------------------


def test_period_key_formats() -> None:
    df = pl.DataFrame(
        {"date": [date(2024, 3, 15), date(2024, 11, 1), date(2026, 4, 2)]}
    )
    assert MetricsBuilder._add_period(df, "yearly").get_column("period").to_list() == [
        "2024",
        "2024",
        "2026",
    ]
    assert MetricsBuilder._add_period(df, "quarterly").get_column(
        "period"
    ).to_list() == [
        "2024_1",
        "2024_4",
        "2026_2",
    ]
    assert MetricsBuilder._add_period(df, "monthly").get_column("period").to_list() == [
        "2024_03",
        "2024_11",
        "2026_04",
    ]


def test_period_order_latest_first() -> None:
    assert period_order("yearly", ["2020", "2024", "2015"]) == [
        "2024",
        "2020",
        "2015",
    ]
    assert period_order("quarterly", ["2024_1", "2024_4", "2023_2", "2024_2"]) == [
        "2024_4",
        "2024_2",
        "2024_1",
        "2023_2",
    ]
    assert period_order("monthly", ["2024_01", "2024_11", "2023_12"]) == [
        "2024_11",
        "2024_01",
        "2023_12",
    ]


def test_all_periods_enumerates_full_year_grid() -> None:
    yearly = all_periods("yearly", date(2024, 6, 1), date(2026, 3, 1))
    assert yearly == ["2024", "2025", "2026"]

    quarterly = all_periods("quarterly", date(2024, 6, 1), date(2025, 3, 31))
    # Full 4 quarters per year in range, independent of start/end day.
    assert quarterly == [
        "2024_1",
        "2024_2",
        "2024_3",
        "2024_4",
        "2025_1",
        "2025_2",
        "2025_3",
        "2025_4",
    ]

    monthly = all_periods("monthly", date(2024, 1, 1), date(2024, 12, 31))
    assert monthly == [f"2024_{m:02d}" for m in range(1, 13)]


# ---------------------------------------------------------------------------
# Build end-to-end against synthetic data
# ---------------------------------------------------------------------------


def _geometric_series(
    sd_id: int, start: date, days: int, daily: float
) -> list[tuple[int, date, float]]:
    rows = []
    nav = 10.0
    for i in range(days):
        rows.append((sd_id, start + timedelta(days=i), nav))
        nav *= 1 + daily
    return rows


def test_build_produces_expected_tables_and_shapes(db: Database) -> None:
    # Two funds + benchmark, each growing at a constant daily rate across 2023.
    sd_fund_a, sd_fund_b, sd_bench = 1001, 1002, 120716
    _seed_minimal_plans(db, [sd_fund_a, sd_fund_b])
    start = date(2023, 1, 2)
    rows: list[tuple[int, date, float]] = []
    rows += _geometric_series(sd_fund_a, start, 260, 0.001)
    rows += _geometric_series(sd_fund_b, start, 260, -0.0005)
    rows += _geometric_series(sd_bench, start, 260, 0.0008)
    _seed_nav_table(db, rows)

    cfg = MetricsConfig(
        start_date=date(2023, 1, 1),
    )
    DatabaseMetricsAdapter(db, benchmark_sd_id=sd_bench, config=cfg).build()

    expected = {
        "metrics_basic_yearly",
        "metrics_basic_quarterly",
        "metrics_basic_monthly",
        "metrics_benchmark_yearly",
        "metrics_benchmark_quarterly",
        "metrics_benchmark_monthly",
        "metrics_performance_yearly",
        "metrics_risk_yearly",
        "metrics_risk_quarterly",
        "metrics_risk_monthly",
    }
    rows_names = {
        r[0]
        for r in db.conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name LIKE 'metrics_%'"
        ).fetchall()
    }
    assert expected <= rows_names

    for name in expected:
        # Each table has exactly one row per non-benchmark sd_id.
        row = db.conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()
        assert row is not None and row[0] == 2, f"{name}: {row}"


def test_returns_and_cagr_match_closed_form(db: Database) -> None:
    """For a constant-daily-rate series, annual return and cagr are exact."""
    sd_fund, sd_bench = 2001, 120716
    _seed_minimal_plans(db, [sd_fund])

    # ~252 trading days with +0.001 per day over 2023.
    rows = _geometric_series(sd_fund, date(2023, 1, 2), 252, 0.001)
    rows += _geometric_series(sd_bench, date(2023, 1, 2), 252, 0.0005)
    _seed_nav_table(db, rows)

    cfg = MetricsConfig(start_date=date(2023, 1, 1))
    DatabaseMetricsAdapter(db, benchmark_sd_id=sd_bench, config=cfg).build()

    row = db.conn.execute(
        "SELECT r_2023, cagr_2023, vol_2023, sr_2023 "
        "FROM metrics_basic_yearly WHERE sd_id = ?",
        [sd_fund],
    ).fetchone()
    assert row is not None
    returns, cagr, volatility, success = row

    # returns = ((1.001 ** 251) - 1) * 100 — stored as percentage.
    expected_returns_pct = ((1.001**251) - 1) * 100
    assert returns == pytest.approx(expected_returns_pct, rel=1e-6)

    # cagr = (1 + r_decimal) ** (252 / 252) - 1 = r_decimal, stored ×100.
    assert cagr == pytest.approx(expected_returns_pct, rel=1e-6)

    # All daily returns positive -> success_ratio = 100.0, volatility ~ 0.
    assert success == pytest.approx(100.0, abs=1e-9)
    assert volatility == pytest.approx(0.0, abs=1e-9)


def test_benchmark_metrics_self_regression(db: Database) -> None:
    """A fund == benchmark should have beta=1, alpha=0, r_squared=1."""
    sd_bench = 120716
    _seed_minimal_plans(db, [sd_bench])
    # Use a noisy geometric series so variance is nonzero.
    import random

    random.seed(0)
    rows = []
    nav = 100.0
    d = date(2023, 1, 2)
    for i in range(252):
        rows.append((sd_bench, d + timedelta(days=i), nav))
        nav *= 1 + random.uniform(-0.01, 0.012)
    _seed_nav_table(db, rows)

    cfg = MetricsConfig(start_date=date(2023, 1, 1))
    DatabaseMetricsAdapter(db, benchmark_sd_id=sd_bench, config=cfg).build()

    # Benchmark itself isn't in plans; skip if filtered. Re-seed plans to include it
    # and rebuild so that the benchmark sd_id appears as a fund row.
    _seed_minimal_plans(db, [sd_bench])
    # Because build filters out sd_id == benchmark from `funds`, we need a second
    # sd_id that has identical NAV series to the benchmark for this property.
    sd_copy = 2002
    rows_copy = [(sd_copy, d, v) for (_, d, v) in rows]
    _seed_nav_table(db, rows + rows_copy)
    _seed_minimal_plans(db, [sd_copy])

    DatabaseMetricsAdapter(db, benchmark_sd_id=sd_bench, config=cfg).build()

    r = db.conn.execute(
        "SELECT beta_2023, alpha_2023, r_sq_2023 "
        "FROM metrics_benchmark_yearly WHERE sd_id = ?",
        [sd_copy],
    ).fetchone()
    assert r is not None
    beta, alpha, r_squared = r
    assert beta == pytest.approx(1.0, abs=1e-9)
    assert alpha == pytest.approx(0.0, abs=1e-9)
    assert r_squared == pytest.approx(1.0, abs=1e-9)


def test_coverage_mask_nulls_sparse_months(db: Database) -> None:
    """A fund with only 1 day in a month must have null metrics there."""
    sd_fund, sd_bench = 3001, 120716
    _seed_minimal_plans(db, [sd_fund])

    # Benchmark trades every weekday of Jan 2023 (~22 days).
    bench_rows = []
    d = date(2023, 1, 2)
    nav = 100.0
    while d.month == 1:
        if d.weekday() < 5:
            bench_rows.append((sd_bench, d, nav))
            nav *= 1.001
        d += timedelta(days=1)

    # Fund trades on only one day in Jan.
    fund_rows = [(sd_fund, date(2023, 1, 2), 10.0), (sd_fund, date(2023, 1, 3), 10.01)]

    _seed_nav_table(db, bench_rows + fund_rows)

    cfg = MetricsConfig(
        start_date=date(2023, 1, 1),
        coverage_threshold=0.9,
    )
    DatabaseMetricsAdapter(db, benchmark_sd_id=sd_bench, config=cfg).build()

    r = db.conn.execute(
        "SELECT r_2023_01, vol_2023_01 FROM metrics_basic_monthly WHERE sd_id = ?",
        [sd_fund],
    ).fetchone()
    assert r == (None, None)

    # Yearly bypasses coverage; r should be populated.
    r2 = db.conn.execute(
        "SELECT r_2023 FROM metrics_basic_yearly WHERE sd_id = ?", [sd_fund]
    ).fetchone()
    assert r2 is not None and r2[0] is not None


def test_max_drawdown_is_negative_on_crash(db: Database) -> None:
    """A fund that crashes then recovers should have a clearly negative MDD."""
    sd_fund, sd_bench = 4001, 120716
    _seed_minimal_plans(db, [sd_fund])
    d0 = date(2023, 1, 2)
    rows = [(sd_fund, d0 + timedelta(days=i), 100.0) for i in range(10)]
    # Crash: 100 -> 60 over one day, then hold.
    for i in range(10, 20):
        rows.append((sd_fund, d0 + timedelta(days=i), 60.0))
    # Recover: 60 -> 100 linearly.
    for i in range(20, 30):
        rows.append((sd_fund, d0 + timedelta(days=i), 60 + (i - 20) * 4.0))
    # Benchmark: flat.
    for i in range(30):
        rows.append((sd_bench, d0 + timedelta(days=i), 100.0))
    _seed_nav_table(db, rows)

    cfg = MetricsConfig(start_date=date(2023, 1, 1))
    DatabaseMetricsAdapter(db, benchmark_sd_id=sd_bench, config=cfg).build()

    r = db.conn.execute(
        "SELECT md_2023, ui_2023 FROM metrics_risk_yearly WHERE sd_id = ?",
        [sd_fund],
    ).fetchone()
    assert r is not None
    mdd, ulcer = r
    # md and ui are both scaled ×100 (percentage-style risk metrics).
    assert mdd == pytest.approx(-40.0, abs=1e-9)
    assert ulcer > 0


def test_all_metrics_tables_have_sd_id_first(db: Database) -> None:
    sd_fund, sd_bench = 5001, 120716
    _seed_minimal_plans(db, [sd_fund])
    rows = _geometric_series(sd_fund, date(2023, 1, 2), 260, 0.0003)
    rows += _geometric_series(sd_bench, date(2023, 1, 2), 260, 0.0002)
    _seed_nav_table(db, rows)

    DatabaseMetricsAdapter(
        db, benchmark_sd_id=sd_bench, config=MetricsConfig(start_date=date(2023, 1, 1))
    ).build()

    names = [
        "metrics_basic_yearly",
        "metrics_basic_quarterly",
        "metrics_basic_monthly",
        "metrics_benchmark_yearly",
        "metrics_benchmark_quarterly",
        "metrics_benchmark_monthly",
        "metrics_performance_yearly",
        "metrics_risk_yearly",
        "metrics_risk_quarterly",
        "metrics_risk_monthly",
    ]
    for n in names:
        cols = db.conn.execute(
            f"SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{n}' ORDER BY ordinal_position"
        ).fetchall()
        assert cols[0][0] == "sd_id", f"{n}: first col is {cols[0][0]}"


def test_metrics_table_create_sql_contains_expected_columns() -> None:
    """Factory-generated tables expose one column per (metric, period) pair."""
    from amfi.data.metrics import MetricsBasicYearlyTable

    sql = MetricsBasicYearlyTable.create_sql()
    assert sql.lstrip().startswith("CREATE TABLE IF NOT EXISTS metrics_basic_yearly (")
    # Default MetricsConfig covers 2015..today, so columns must include 2015
    # + the current year; use a broad year likely present in any run window.
    for year in (2015, 2020):
        for metric in ("r", "cagr", "sr", "vol"):
            assert f"{metric}_{year} DOUBLE" in sql


def test_period_views_expose_plans_columns(db: Database) -> None:
    sd_fund, sd_bench = 6001, 120716
    _seed_minimal_plans(db, [sd_fund])
    rows = _geometric_series(sd_fund, date(2026, 1, 2), 60, 0.001)
    rows += _geometric_series(sd_bench, date(2026, 1, 2), 60, 0.0005)
    _seed_nav_table(db, rows)

    cfg = MetricsConfig(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    DatabaseMetricsAdapter(db, benchmark_sd_id=sd_bench, config=cfg).build()

    # Yearly view carries sd_id + scheme + aum + every metric family.
    cols = [
        r[0]
        for r in db.conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'metrics_2026' ORDER BY ordinal_position"
        ).fetchall()
    ]
    assert cols[:2] == ["sd_id", "scheme"]
    for m in ("r_2026", "cagr_2026", "md_2026", "beta_2026", "sharpe_2026"):
        assert m in cols, f"metrics_2026 missing {m}"

    # Quarterly view has no performance columns.
    qcols = [
        r[0]
        for r in db.conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'metrics_2026_1' ORDER BY ordinal_position"
        ).fetchall()
    ]
    assert qcols[:2] == ["sd_id", "scheme"]
    assert "r_2026_1" in qcols
    assert "sharpe_2026_1" not in qcols
    assert "sortino_2026_1" not in qcols

    # Monthly view exists with zero-padded suffix.
    mcols = [
        r[0]
        for r in db.conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'metrics_2026_01' ORDER BY ordinal_position"
        ).fetchall()
    ]
    assert mcols[:2] == ["sd_id", "scheme"]
    assert "r_2026_01" in mcols

    # Row count anchored on plans.
    for view in ("metrics_2026", "metrics_2026_1", "metrics_2026_01"):
        row = db.conn.execute(f"SELECT COUNT(*) FROM {view}").fetchone()
        assert row is not None and row[0] == 1, f"{view}: {row}"


# ---------------------------------------------------------------------------
# Sharpe / Sortino formulas
# ---------------------------------------------------------------------------


def _noisy_series(
    sd_id: int, start: date, days: int, mean: float, vol: float, seed: int
) -> list[tuple[int, date, float]]:
    """Geometric series with i.i.d. normal-ish daily returns (uniform proxy)."""
    import random

    rng = random.Random(seed)
    rows = []
    nav = 100.0
    for i in range(days):
        rows.append((sd_id, start + timedelta(days=i), nav))
        # Uniform on [mean - vol*sqrt(3), mean + vol*sqrt(3)] -> std = vol.
        spread = vol * (3**0.5)
        nav *= 1 + mean + rng.uniform(-spread, spread)
    return rows


def test_sharpe_invariant_to_period_length(db: Database) -> None:
    """Annualised Sharpe should be the same for full-year vs partial-year.

    Uses a deterministic 5-day return pattern repeated across two years so
    that both windows have identical sample mean and std; the only thing
    that changes is the number of observations. After the annualisation
    fix, Sharpe must match to high precision; before the fix the partial
    window came out ~n/td of the full value.
    """
    sd_full, sd_partial, sd_bench = 7001, 7002, 120716
    _seed_minimal_plans(db, [sd_full, sd_partial])

    pattern = [0.002, -0.001, 0.0015, -0.0005, 0.001]  # mean ~0.0008, std>0

    def _patterned_series(
        sd: int, start: date, days: int
    ) -> list[tuple[int, date, float]]:
        rows = []
        nav = 100.0
        for i in range(days):
            rows.append((sd, start + timedelta(days=i), nav))
            nav *= 1 + pattern[i % len(pattern)]
        return rows

    rows: list[tuple[int, date, float]] = []
    # Full 2025: 250 days = 50 full pattern cycles.
    rows += _patterned_series(sd_full, date(2025, 1, 2), 250)
    # Partial 2026: 80 days = 16 full pattern cycles (same population stats).
    rows += _patterned_series(sd_partial, date(2026, 1, 2), 80)
    # Benchmark covers both years.
    rows += _patterned_series(sd_bench, date(2025, 1, 2), 250)
    rows += _patterned_series(sd_bench, date(2026, 1, 2), 80)
    _seed_nav_table(db, rows)

    cfg = MetricsConfig(
        start_date=date(2025, 1, 1),
        end_date=date(2026, 12, 31),
        risk_free_rate=0.07,
    )
    DatabaseMetricsAdapter(db, benchmark_sd_id=sd_bench, config=cfg).build()

    sharpe_full = db.conn.execute(
        "SELECT sharpe_2025 FROM metrics_performance_yearly WHERE sd_id = ?",
        [sd_full],
    ).fetchone()
    sharpe_partial = db.conn.execute(
        "SELECT sharpe_2026 FROM metrics_performance_yearly WHERE sd_id = ?",
        [sd_partial],
    ).fetchone()
    assert sharpe_full is not None and sharpe_full[0] is not None
    assert sharpe_partial is not None and sharpe_partial[0] is not None
    # Identical daily-return distribution => annualised Sharpe matches up to
    # tiny ddof differences from sample size. Pre-fix the ratio was ~80/252.
    assert sharpe_partial[0] == pytest.approx(sharpe_full[0], rel=0.05)


def test_sortino_null_when_no_negative_returns(db: Database) -> None:
    """All-positive daily returns -> downside_dev = 0 -> Sortino is NULL."""
    sd_fund, sd_bench = 7101, 120716
    _seed_minimal_plans(db, [sd_fund])
    rows = _geometric_series(sd_fund, date(2025, 1, 2), 252, 0.0002)
    rows += _geometric_series(sd_bench, date(2025, 1, 2), 252, 0.0001)
    _seed_nav_table(db, rows)

    cfg = MetricsConfig(start_date=date(2025, 1, 1))
    DatabaseMetricsAdapter(db, benchmark_sd_id=sd_bench, config=cfg).build()

    row = db.conn.execute(
        "SELECT sortino_2025 FROM metrics_performance_yearly WHERE sd_id = ?",
        [sd_fund],
    ).fetchone()
    assert row is not None
    assert row[0] is None


def test_sortino_matches_closed_form(db: Database) -> None:
    """Sortino denominator equals sqrt(sum(min(ret,0)^2) / (n-1))."""
    import math

    sd_fund, sd_bench = 7201, 120716
    _seed_minimal_plans(db, [sd_fund])

    # Construct a series with deterministic daily returns so we can reproduce
    # the Sortino value by hand. Use a 252-day series with 200 +0.001 days
    # and 52 -0.002 days, interleaved.
    rets = ([0.001] * 4 + [-0.002]) * 50 + [0.001] * 2  # 252 daily returns
    assert len(rets) == 252
    rows: list[tuple[int, date, float]] = []
    nav = 100.0
    d0 = date(2025, 1, 2)
    rows.append((sd_fund, d0, nav))
    for i, r in enumerate(rets):
        nav *= 1 + r
        rows.append((sd_fund, d0 + timedelta(days=i + 1), nav))
    # Benchmark: arbitrary positive series.
    rows += _geometric_series(sd_bench, d0, 253, 0.0003)
    _seed_nav_table(db, rows)

    cfg = MetricsConfig(
        start_date=date(2025, 1, 1),
        risk_free_rate=0.05,
    )
    DatabaseMetricsAdapter(db, benchmark_sd_id=sd_bench, config=cfg).build()

    sortino = db.conn.execute(
        "SELECT sortino_2025 FROM metrics_performance_yearly WHERE sd_id = ?",
        [sd_fund],
    ).fetchone()
    assert sortino is not None and sortino[0] is not None

    # Reproduce: the daily returns inside the 2025 period are exactly `rets`
    # (the first row at d0 has no return). n_ret = 252.
    n_ret = len(rets)
    mean_r = sum(rets) / n_ret
    neg_sq = sum(r * r for r in rets if r < 0)
    downside_dev = math.sqrt(neg_sq / (n_ret - 1))
    td = 252.0
    expected = (mean_r * td - 0.05) / (downside_dev * math.sqrt(td))
    assert sortino[0] == pytest.approx(expected, rel=1e-6)


def test_m2_dimensionally_annualised(db: Database) -> None:
    """For a fund with the same daily series as the benchmark, M² should
    be the annualised return of the benchmark itself (sigma_fund = sigma_bench
    => M² = R_bench_annualised)."""
    sd_copy, sd_bench = 7301, 120716
    _seed_minimal_plans(db, [sd_copy])
    # Noisy benchmark series; copy the same NAVs to the fund.
    bench_rows = _noisy_series(sd_bench, date(2025, 1, 2), 252, 0.0008, 0.01, seed=11)
    fund_rows = [(sd_copy, d, v) for (_, d, v) in bench_rows]
    _seed_nav_table(db, bench_rows + fund_rows)

    cfg = MetricsConfig(
        start_date=date(2025, 1, 1),
        risk_free_rate=0.07,
    )
    DatabaseMetricsAdapter(db, benchmark_sd_id=sd_bench, config=cfg).build()

    row = db.conn.execute(
        "SELECT m2_2025 FROM metrics_benchmark_yearly WHERE sd_id = ?",
        [sd_copy],
    ).fetchone()
    assert row is not None and row[0] is not None
    # M² is annualised (decimal). For a typical noisy series with mean 0.0008/day
    # and vol ~0.01, annualised return ≈ 0.0008*252 ≈ 0.20 with wide tolerance.
    # The key invariant we test is that the value is in a sane decimal range,
    # not a period-scale fragment.
    assert 0.0 < row[0] < 1.0


# ---------------------------------------------------------------------------
# Pure-polars MetricsBuilder tests (no DuckDB)
# ---------------------------------------------------------------------------


def _make_pivoted_df(
    fund_navs: dict[str, list[float]],
    bench_navs: list[float],
    bench_name: str,
    start: date,
) -> pl.DataFrame:
    """Build a pivoted DataFrame from daily NAV lists."""

    n = max(len(bench_navs), *(len(v) for v in fund_navs.values()))
    dates = [start + timedelta(days=i) for i in range(n)]
    data: dict[str, list] = {"date": dates}
    data[bench_name] = bench_navs + [None] * (n - len(bench_navs))
    for name, navs in fund_navs.items():
        data[name] = navs + [None] * (n - len(navs))
    return pl.DataFrame(data).with_columns(pl.col("date").cast(pl.Date))


def test_pure_builder_returns_wide_df() -> None:
    """MetricsBuilder returns one row per fund with metric_period columns."""
    # 252-day constant-growth fund + benchmark
    days = 252
    bench = [10.0 * (1.0005**i) for i in range(days)]
    fund = [10.0 * (1.001**i) for i in range(days)]
    df = _make_pivoted_df({"FundA": fund}, bench, "Bench", date(2025, 1, 2))

    result = MetricsBuilder(
        df,
        benchmark="Bench",
        frequency="yearly",
        metrics=["r", "cagr"],
        config=MetricsConfig(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)),
    ).build()

    assert isinstance(result, pl.DataFrame)
    assert result.height == 2  # fund + benchmark
    assert sorted(result.get_column("scheme").to_list()) == ["Bench", "FundA"]
    # r_2025 and cagr_2025 columns exist
    assert "r_2025" in result.columns
    assert "cagr_2025" in result.columns


def test_pure_builder_basic_metrics_values() -> None:
    """Verify returns match closed-form for constant-growth series."""
    days = 252
    daily_r = 0.001
    bench = [10.0 * (1.0005**i) for i in range(days)]
    fund = [10.0 * (1 + daily_r) ** i for i in range(days)]
    df = _make_pivoted_df({"FundA": fund}, bench, "Bench", date(2025, 1, 2))

    result = MetricsBuilder(
        df,
        benchmark="Bench",
        frequency="yearly",
        metrics=["r", "cagr", "sr", "vol"],
        config=MetricsConfig(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)),
    ).build()

    r_val = result.filter(pl.col("scheme") == "FundA").get_column("r_2025")[0]
    # returns = ((1.001 ** 251) - 1) * 100 stored as percentage
    expected_r = ((1 + daily_r) ** 251 - 1) * 100
    assert r_val == pytest.approx(expected_r, rel=1e-6)

    # Success ratio should be 100% (all positive returns)
    sr_val = result.filter(pl.col("scheme") == "FundA").get_column("sr_2025")[0]
    assert sr_val == pytest.approx(100.0, abs=1e-9)

    # Volatility ~0 for constant-growth
    vol_val = result.filter(pl.col("scheme") == "FundA").get_column("vol_2025")[0]
    assert vol_val == pytest.approx(0.0, abs=1e-9)


def test_pure_builder_benchmark_metrics() -> None:
    """Fund identical to benchmark → beta=1, alpha≈0, r_sq=1."""
    import random

    random.seed(42)
    days = 252
    navs = [100.0]
    for _ in range(days - 1):
        navs.append(navs[-1] * (1 + random.uniform(-0.01, 0.012)))

    df = _make_pivoted_df({"FundCopy": navs}, navs, "Bench", date(2025, 1, 2))

    result = MetricsBuilder(
        df,
        benchmark="Bench",
        frequency="yearly",
        metrics=["beta", "alpha", "r_sq"],
        config=MetricsConfig(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)),
    ).build()

    assert result.height == 1
    assert result.get_column("scheme").to_list() == ["FundCopy"]
    assert result.get_column("beta_2025")[0] == pytest.approx(1.0, abs=1e-9)
    assert result.get_column("alpha_2025")[0] == pytest.approx(0.0, abs=1e-9)
    assert result.get_column("r_sq_2025")[0] == pytest.approx(1.0, abs=1e-9)


def test_pure_builder_performance_yearly_only() -> None:
    """Performance metrics (sharpe, sortino) only produced for yearly frequency."""
    days = 60
    bench = [10.0 * (1.0005**i) for i in range(days)]
    fund = [10.0 * (1.001**i) for i in range(days)]
    df = _make_pivoted_df({"F": fund}, bench, "B", date(2025, 1, 2))

    # Monthly: sharpe/sortino should NOT appear
    result_monthly = MetricsBuilder(
        df,
        benchmark="B",
        frequency="monthly",
        metrics=["sharpe", "sortino"],
        config=MetricsConfig(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)),
    ).build()
    # No sharpe/sortino columns for monthly
    assert not any(c.startswith("sharpe_") for c in result_monthly.columns)
    assert not any(c.startswith("sortino_") for c in result_monthly.columns)

    # Yearly: sharpe/sortino should appear
    result_yearly = MetricsBuilder(
        df,
        benchmark="B",
        frequency="yearly",
        metrics=["sharpe", "sortino"],
        config=MetricsConfig(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)),
    ).build()
    assert any(c.startswith("sharpe_") for c in result_yearly.columns)


def test_pure_builder_multiple_funds() -> None:
    """Builder handles multiple funds correctly."""
    days = 100
    bench = [10.0 * (1.0005**i) for i in range(days)]
    fund_a = [10.0 * (1.001**i) for i in range(days)]
    fund_b = [10.0 * (1.0008**i) for i in range(days)]
    df = _make_pivoted_df(
        {"FundA": fund_a, "FundB": fund_b}, bench, "Bench", date(2025, 1, 2)
    )

    result = MetricsBuilder(
        df,
        benchmark="Bench",
        frequency="yearly",
        metrics=["r"],
        config=MetricsConfig(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)),
    ).build()

    assert result.height == 3  # includes benchmark
    schemes = sorted(result.get_column("scheme").to_list())
    assert schemes == ["Bench", "FundA", "FundB"]


if __name__ == "__main__":
    pytest.main([__file__, "-q", "--tb=short"])
