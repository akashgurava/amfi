"""Unit tests for :mod:`amfi.portfolios`."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest

from amfi.data import RawNavResponse
from amfi.db import Database
from amfi.error import AppConfigError
from amfi.portfolios import (
    PORTFOLIO_ID_OFFSET,
    PortfolioBuilder,
    PortfolioConfig,
    load_portfolios,
)

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    d = Database(db_path=str(tmp_path / "p.duckdb"))
    d.create_database_objects()
    yield d
    d.close()


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


def _seed_plans_funds(
    db: Database, rows: list[tuple[int, str, str, float, date, date, date]]
) -> None:
    """Create a synthetic ``plans_funds`` with the same schema as production.

    Each row: (sd_id, scheme, plan, aum, launch_date, start_date, latest_date).
    """
    db.conn.execute("DROP TABLE IF EXISTS plans_funds")
    db.conn.execute(
        """
        CREATE TABLE plans_funds (
            fund_house_id INTEGER, fund_house VARCHAR,
            scheme_id INTEGER, scheme VARCHAR,
            sd_id INTEGER, plan VARCHAR,
            scheme_type VARCHAR,
            category VARCHAR, subcategory VARCHAR,
            tax DECIMAL(4,3),
            aum DOUBLE,
            launch_date DATE, start_date DATE, latest_date DATE,
            latest_nav DOUBLE,
            is_in_use BOOLEAN, is_not_lockin BOOLEAN, is_retail BOOLEAN,
            is_etf BOOLEAN, is_growth BOOLEAN, is_direct BOOLEAN
        )
        """
    )
    for sd, scheme, plan, aum, launch, start, latest in rows:
        db.conn.execute(
            "INSERT INTO plans_funds VALUES (?,?,?,?,?,?,'Open Ended',"
            "'equity','flexi cap',0.125,?,?,?,?,10.0,"
            "TRUE,TRUE,TRUE,FALSE,TRUE,TRUE)",
            [1, "HDFC AMC", sd, scheme, sd, plan, aum, launch, start, latest],
        )


def _seed_tax_cat(db: Database) -> None:
    db.conn.execute("DROP TABLE IF EXISTS tax_cat")
    db.conn.execute(
        "CREATE TABLE tax_cat (category VARCHAR, subcategory VARCHAR, tax DOUBLE)"
    )
    db.conn.execute(
        "INSERT INTO tax_cat VALUES "
        "('equity', 'flexi cap', 0.125), "
        "('equity', 'multi cap', 0.125), "
        "('other', 'index funds', 0.125)"
    )


def _seed_nav_funds(db: Database, rows: list[tuple[int, date, float]]) -> None:
    db.conn.execute("DROP TABLE IF EXISTS nav_funds")
    db.conn.execute(
        "CREATE TABLE nav_funds (sd_id INTEGER, date DATE, nav DOUBLE, raw_nav DOUBLE)"
    )
    db.conn.executemany(
        "INSERT INTO nav_funds VALUES (?,?,?,?)",
        [(sd, d, v, v) for sd, d, v in rows],
    )


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def test_load_portfolios_happy_path(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yml"
    cfg.write_text(
        """
portfolios:
  HDFC All Cap Conservative:
    fund_house_id: 9
    category: other
    subcategory: index funds
    start_date: '2025-01-01'
    weights:
      149870: 50000
      151724: 30000
      151727: 20000
  HDFC All Cap Aggressive:
    weights:
      149870: 30000
      151724: 40000
      151727: 30000
"""
    )
    out = load_portfolios(cfg)
    assert len(out) == 2

    conservative = out[0]
    assert conservative.name == "HDFC All Cap Conservative"
    assert conservative.index == 0
    assert conservative.fund_house_id == 9
    assert conservative.category == "other"
    assert conservative.subcategory == "index funds"
    assert conservative.start_date == date(2025, 1, 1)
    assert conservative.weights == {149870: 50000.0, 151724: 30000.0, 151727: 20000.0}

    aggressive = out[1]
    assert aggressive.name == "HDFC All Cap Aggressive"
    assert aggressive.index == 1
    # Defaults kick in when omitted.
    assert aggressive.fund_house_id is None
    assert aggressive.category is None
    assert aggressive.start_date is None


def test_load_portfolios_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_portfolios(tmp_path / "absent.yml") == []


def test_load_portfolios_empty_block_returns_empty(tmp_path: Path) -> None:
    cfg = tmp_path / "c.yml"
    cfg.write_text("portfolios:\n")
    assert load_portfolios(cfg) == []


def test_load_portfolios_rejects_list_format(tmp_path: Path) -> None:
    cfg = tmp_path / "c.yml"
    cfg.write_text("portfolios:\n  - Foo\n")
    with pytest.raises(AppConfigError):
        load_portfolios(cfg)


def test_load_portfolios_rejects_missing_weights(tmp_path: Path) -> None:
    cfg = tmp_path / "c.yml"
    cfg.write_text("portfolios:\n  Foo:\n    category: equity\n")
    with pytest.raises(AppConfigError):
        load_portfolios(cfg)


def test_load_portfolios_rejects_non_positive_weight(tmp_path: Path) -> None:
    cfg = tmp_path / "c.yml"
    cfg.write_text("portfolios:\n  Foo:\n    weights:\n      1: 0\n")
    with pytest.raises(AppConfigError):
        load_portfolios(cfg)


# ---------------------------------------------------------------------------
# Synthetic IDs and defaults
# ---------------------------------------------------------------------------


def test_synthetic_ids_are_deterministic() -> None:
    p0 = PortfolioConfig(name="A", index=0, weights={1: 1.0})
    p1 = PortfolioConfig(name="B", index=1, weights={1: 1.0})
    assert p0.sd_id == PORTFOLIO_ID_OFFSET + 1
    assert p0.scheme_id == PORTFOLIO_ID_OFFSET + 1
    assert p0.effective_fund_house_id == PORTFOLIO_ID_OFFSET + 1
    assert p1.sd_id == PORTFOLIO_ID_OFFSET + 2
    assert p1.effective_fund_house_id == PORTFOLIO_ID_OFFSET + 2


def test_synthetic_ids_respect_config_fund_house_id() -> None:
    p = PortfolioConfig(name="X", index=0, weights={1: 1.0}, fund_house_id=9)
    assert p.effective_fund_house_id == 9
    # sd_id / scheme_id stay synthetic regardless.
    assert p.sd_id == PORTFOLIO_ID_OFFSET + 1


def test_effective_defaults() -> None:
    p = PortfolioConfig(name="Port", index=0, weights={1: 1.0})
    assert p.effective_fund_house == "Port"
    assert p.effective_category == "equity"
    assert p.effective_subcategory == "multi cap"


# ---------------------------------------------------------------------------
# PortfolioBuilder: build_plans
# ---------------------------------------------------------------------------


def test_build_plans_aggregates_constituent_metadata(db: Database) -> None:
    _seed_tax_cat(db)
    _seed_plans_funds(
        db,
        rows=[
            # (sd_id, scheme, plan, aum, launch, start, latest)
            (
                100,
                "Fund A",
                "Fund A - Dir",
                500.0,
                date(2015, 1, 1),
                date(2015, 6, 1),
                date(2026, 4, 1),
            ),
            (
                200,
                "Fund B",
                "Fund B - Dir",
                800.0,
                date(2018, 3, 15),
                date(2018, 7, 1),
                date(2026, 3, 31),
            ),
            (
                300,
                "Fund C",
                "Fund C - Dir",
                300.0,
                date(2020, 11, 1),
                date(2020, 12, 1),
                date(2026, 4, 2),
            ),
        ],
    )

    p = PortfolioConfig(
        name="Demo Port",
        index=0,
        weights={100: 1000.0, 200: 2000.0, 300: 3000.0},
    )
    PortfolioBuilder(db, [p]).build_plans()

    row = db.conn.execute(
        """
        SELECT fund_house_id, fund_house, scheme_id, scheme, sd_id, plan,
               scheme_type, category, subcategory, tax,
               aum, launch_date, start_date, latest_date, latest_nav,
               is_in_use, is_not_lockin, is_retail, is_etf, is_growth, is_direct
        FROM plans_portfolios
        """
    ).fetchone()
    assert row is not None
    (
        fh_id,
        fh,
        sid,
        scheme,
        sd,
        plan,
        stype,
        cat,
        sub,
        tax,
        aum,
        launch,
        start,
        latest,
        latest_nav,
        in_use,
        no_lock,
        retail,
        etf,
        growth,
        direct,
    ) = row

    assert fh_id == PORTFOLIO_ID_OFFSET + 1
    assert fh == "Demo Port"
    assert sid == PORTFOLIO_ID_OFFSET + 1
    assert scheme == "Demo Port"
    assert sd == PORTFOLIO_ID_OFFSET + 1
    assert plan == "Demo Port"
    assert stype == "Open Ended"
    assert cat == "equity"
    assert sub == "multi cap"
    # multi cap is not in the seeded tax_cat -> NULL is acceptable.
    assert tax is None or float(tax) == 0.125
    # Aggregates.
    assert aum == 300.0  # min aum
    assert launch == date(2020, 11, 1)  # max launch
    assert start == date(2020, 12, 1)  # max start
    assert latest == date(2026, 3, 31)  # min latest
    assert latest_nav == 100.0
    assert (in_use, no_lock, retail, etf, growth, direct) == (
        True,
        True,
        True,
        True,
        True,
        True,
    )


def test_build_plans_respects_config_overrides(db: Database) -> None:
    _seed_tax_cat(db)
    _seed_plans_funds(
        db,
        rows=[
            (
                100,
                "Fund A",
                "Fund A - Dir",
                500.0,
                date(2015, 1, 1),
                date(2015, 6, 1),
                date(2026, 4, 1),
            ),
        ],
    )

    p = PortfolioConfig(
        name="Configured",
        index=0,
        weights={100: 1000.0},
        fund_house_id=42,
        fund_house="Custom House",
        category="other",
        subcategory="index funds",
        start_date=date(2023, 1, 1),
    )
    PortfolioBuilder(db, [p]).build_plans()

    row = db.conn.execute(
        "SELECT fund_house_id, fund_house, category, subcategory, "
        "start_date, tax FROM plans_portfolios"
    ).fetchone()
    assert row is not None
    assert row[0] == 42
    assert row[1] == "Custom House"
    assert row[2] == "other"
    assert row[3] == "index funds"
    # start_date from config, not from constituents.
    assert row[4] == date(2023, 1, 1)
    # tax joined from tax_cat.
    assert row[5] is not None and float(row[5]) == 0.125


def test_build_plans_skips_unknown_constituents(db: Database) -> None:
    _seed_tax_cat(db)
    _seed_plans_funds(db, rows=[])  # empty plans_funds

    p = PortfolioConfig(name="Ghost", index=0, weights={999: 1000.0})
    PortfolioBuilder(db, [p]).build_plans()
    row = db.conn.execute("SELECT COUNT(*) FROM plans_portfolios").fetchone()
    assert row is not None and row[0] == 0


# ---------------------------------------------------------------------------
# PortfolioBuilder: build_nav
# ---------------------------------------------------------------------------


def _build_with_two_constituents(
    db: Database,
    p: PortfolioConfig,
    a_series: list[tuple[date, float]],
    b_series: list[tuple[date, float]],
) -> None:
    _seed_tax_cat(db)
    _seed_plans_funds(
        db,
        rows=[
            (
                100,
                "A",
                "A - Dir",
                100.0,
                date(2022, 1, 1),
                a_series[0][0],
                a_series[-1][0],
            ),
            (
                200,
                "B",
                "B - Dir",
                100.0,
                date(2022, 1, 1),
                b_series[0][0],
                b_series[-1][0],
            ),
        ],
    )
    _seed_nav_funds(
        db,
        [(100, d, v) for d, v in a_series] + [(200, d, v) for d, v in b_series],
    )
    PortfolioBuilder(db, [p]).build()


def test_build_nav_normalises_to_100_at_start(db: Database) -> None:
    # Two constituents, 50/50 weight, growing at different rates.
    d0 = date(2024, 1, 1)
    a_series = [(d0 + timedelta(days=i), 100.0 * (1.01**i)) for i in range(5)]
    b_series = [(d0 + timedelta(days=i), 50.0 * (1.005**i)) for i in range(5)]

    p = PortfolioConfig(
        name="Half Half",
        index=0,
        weights={100: 5000.0, 200: 5000.0},
    )
    _build_with_two_constituents(db, p, a_series, b_series)

    rows = db.conn.execute(
        "SELECT date, nav FROM nav_portfolios ORDER BY date"
    ).fetchall()
    assert len(rows) == 5
    # Start day: normalised to 100.
    assert rows[0][1] == pytest.approx(100.0, abs=1e-9)
    # Day 4: units = 5000/100 (A) + 5000/50 (B) = 50 + 100 = 150 units worth.
    # value_0 = 50*100 + 100*50 = 10_000. value_4 = 50*100*1.01**4 + 100*50*1.005**4
    units_a = 5000.0 / 100.0
    units_b = 5000.0 / 50.0
    v0 = units_a * 100.0 + units_b * 50.0
    v4 = units_a * a_series[4][1] + units_b * b_series[4][1]
    expected_nav4 = v4 / v0 * 100.0
    assert rows[4][1] == pytest.approx(expected_nav4, rel=1e-9)


def test_build_nav_inner_joins_dates(db: Database) -> None:
    """Dates missing from any constituent are dropped from the portfolio."""
    a_series = [
        (date(2024, 1, 1), 100.0),
        (date(2024, 1, 2), 101.0),
        (date(2024, 1, 3), 102.0),  # only A has this date
        (date(2024, 1, 4), 103.0),
    ]
    b_series = [
        (date(2024, 1, 1), 50.0),
        (date(2024, 1, 2), 50.5),
        (date(2024, 1, 4), 51.0),
    ]
    p = PortfolioConfig(
        name="Gap",
        index=0,
        weights={100: 1000.0, 200: 1000.0},
    )
    _build_with_two_constituents(db, p, a_series, b_series)

    dates = [
        r[0]
        for r in db.conn.execute(
            "SELECT date FROM nav_portfolios ORDER BY date"
        ).fetchall()
    ]
    assert dates == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 4)]


def test_build_nav_respects_config_start_date(db: Database) -> None:
    d0 = date(2024, 1, 1)
    a_series = [(d0 + timedelta(days=i), 100.0 + i) for i in range(10)]
    b_series = [(d0 + timedelta(days=i), 50.0 + 0.1 * i) for i in range(10)]
    p = PortfolioConfig(
        name="LateStart",
        index=0,
        weights={100: 1000.0, 200: 1000.0},
        start_date=d0 + timedelta(days=5),
    )
    _build_with_two_constituents(db, p, a_series, b_series)

    rows = db.conn.execute(
        "SELECT date, nav FROM nav_portfolios ORDER BY date"
    ).fetchall()
    assert len(rows) == 5  # days 5..9
    assert rows[0][0] == d0 + timedelta(days=5)
    assert rows[0][1] == pytest.approx(100.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Full pipeline: plans/nav UNION views see portfolio rows
# ---------------------------------------------------------------------------


def test_full_build_surfaces_portfolios_in_plans_and_nav_views(
    tmp_path: Path,
) -> None:
    """End-to-end: build from raw tables + yaml; plans/nav include portfolio."""
    db = Database(db_path=str(tmp_path / "e2e.duckdb"))
    try:
        db.create_database_objects()
        # Two constituent funds, 1-year daily NAVs.
        from amfi.data import RawFundHouseResponse, RawNavPlanDetailsResponse

        db.insert_fund_houses(
            [
                RawFundHouseResponse.from_dict(
                    {"mf_id": "1", "mf_name": "HDFC AMC", "amc_name": "AMC"}
                )
            ]
        )
        db.conn.execute(
            """
            INSERT INTO raw_scheme (
                mf_id, mf_name, scheme_id, scheme_name, scheme_objective,
                scheme_type_desc, scheme_cat_desc, launch_date, scheme_load,
                scheme_min_amt, amc_website
            ) VALUES
              ('1','HDFC AMC','100','Fund A','obj','Open Ended',
               'Equity - Flexi Cap Fund','2020-01-01','','',''),
              ('1','HDFC AMC','200','Fund B','obj','Open Ended',
               'Equity - Flexi Cap Fund','2020-01-01','','','')
            """
        )
        db.insert_or_ignore_nav_plan_details(
            [
                RawNavPlanDetailsResponse(
                    sd_id="100",
                    fund_house="HDFC AMC",
                    scheme="Fund A",
                    plan="Fund A - Direct Plan - Growth",
                ),
                RawNavPlanDetailsResponse(
                    sd_id="200",
                    fund_house="HDFC AMC",
                    scheme="Fund B",
                    plan="Fund B - Direct Plan - Growth",
                ),
            ]
        )

        today = date.today()
        start = today - timedelta(days=30)
        navs: list[RawNavResponse] = []
        for i in range(31):
            navs.append(_nav_row("100", start + timedelta(days=i), 100.0 + i))
            navs.append(_nav_row("200", start + timedelta(days=i), 50.0 + 0.5 * i))
        db.bulk_insert_nav(navs)

        cfg = tmp_path / "config.yml"
        cfg.write_text(
            """
portfolios:
  Demo Port:
    weights:
      100: 1000
      200: 1000
"""
        )
        db.build(config_path=cfg)

        plans_count = db.conn.execute("SELECT COUNT(*) FROM plans").fetchone()
        plans_funds_count = db.conn.execute(
            "SELECT COUNT(*) FROM plans_funds"
        ).fetchone()
        portfolio_row = db.conn.execute(
            "SELECT sd_id, scheme FROM plans WHERE sd_id = ?",
            [PORTFOLIO_ID_OFFSET + 1],
        ).fetchone()

        assert plans_count is not None
        assert plans_funds_count is not None
        assert plans_count[0] == plans_funds_count[0] + 1
        assert portfolio_row is not None
        assert portfolio_row[1] == "Demo Port"

        # nav view contains portfolio rows normalised to 100 at start.
        portfolio_nav = db.conn.execute(
            "SELECT MIN(nav), MAX(date), COUNT(*) FROM nav WHERE sd_id = ?",
            [PORTFOLIO_ID_OFFSET + 1],
        ).fetchone()
        assert portfolio_nav is not None and portfolio_nav[2] > 0

        # Metrics tables also include the portfolio.
        metric_row = db.conn.execute(
            "SELECT sd_id FROM metrics_basic_monthly WHERE sd_id = ?",
            [PORTFOLIO_ID_OFFSET + 1],
        ).fetchone()
        assert metric_row is not None and metric_row[0] == PORTFOLIO_ID_OFFSET + 1
    finally:
        db.close()


def test_build_without_config_leaves_empty_portfolios(tmp_path: Path) -> None:
    """``config_path=None`` -> plans/nav views reflect only fund rows."""
    db = Database(db_path=str(tmp_path / "nocfg.duckdb"))
    try:
        db.create_database_objects()
        db.build(config_path=None)
        for name in ("plans_portfolios", "nav_portfolios"):
            row = db.conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()
            assert row is not None and row[0] == 0
    finally:
        db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q", "--tb=short"])
