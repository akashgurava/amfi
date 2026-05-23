"""Tests for the derived-view/table layer in :mod:`amfi.data`."""

from __future__ import annotations

from pathlib import Path

import pytest

from amfi.data import (
    DERIVED_OBJECTS,
    NavActiveView,
    NavFundsTable,
    NavView,
    PlansActiveView,
    PlansFundsTable,
    PlansView,
    RawFundHouseResponse,
    RawNavPlanDetailsResponse,
    RawNavResponse,
    TaxCategoryTable,
)
from amfi.data.base import DerivedTable, DerivedView
from amfi.db import Database


def _init_db(db: Database) -> None:
    """Create every schema via the single unified entrypoint."""
    db.create_database_objects()


def test_derived_objects_registration_and_order() -> None:
    expected_order = [
        "plans_active_v",
        "tax_cat",
        "nav_active_v",
        "plans_funds",
        "plans_portfolios",
        "nav_funds",
        "nav_portfolios",
        "plans",
        "nav",
    ]
    names = [cls.name() for cls in DERIVED_OBJECTS]
    assert names == expected_order


def test_derived_view_create_uses_replace_view_prefix() -> None:
    sql = PlansActiveView.create_sql()
    assert sql.lstrip().startswith("CREATE OR REPLACE VIEW plans_active_v AS")
    # Guard against regressions in fixed AS placements.
    assert ") AS is_etf" in sql
    assert ") AS is_growth" in sql
    assert ") AS is_direct" in sql


def test_derived_table_create_is_create_table() -> None:
    """DerivedTable.create_sql emits a plain CREATE TABLE over ``columns()``."""
    plans_sql = PlansFundsTable.create_sql()
    assert plans_sql.lstrip().startswith("CREATE TABLE IF NOT EXISTS plans_funds (")
    assert "sd_id INTEGER" in plans_sql

    nav_sql = NavFundsTable.create_sql()
    assert nav_sql.lstrip().startswith("CREATE TABLE IF NOT EXISTS nav_funds (")

    # Replace flag switches the prefix.
    replace_sql = PlansFundsTable.create_sql(if_not_exists=False, replace=True)
    assert replace_sql.lstrip().startswith("CREATE OR REPLACE TABLE plans_funds (")


def test_union_views_are_views() -> None:
    assert PlansView.create_sql().lstrip().startswith("CREATE OR REPLACE VIEW plans AS")
    assert NavView.create_sql().lstrip().startswith("CREATE OR REPLACE VIEW nav AS")


def test_tax_cat_sourced_from_plans_active_v_not_plans() -> None:
    """Guard the acyclic-DAG decision: tax_cat must not depend on plans."""
    sql = TaxCategoryTable.select_sql()
    assert "plans_active_v" in sql
    assert "FROM plans\n" not in sql
    assert "FROM plans " not in sql


def test_nav_active_is_view() -> None:
    assert (
        NavActiveView.create_sql()
        .lstrip()
        .startswith("CREATE OR REPLACE VIEW nav_active_v AS")
    )


def _fh(mf_id: str, mf_name: str = "Test MF") -> RawFundHouseResponse:
    return RawFundHouseResponse.from_dict(
        {"mf_id": mf_id, "mf_name": mf_name, "amc_name": "AMC"}
    )


def _npd(
    sd_id: str, scheme: str, plan: str, fund_house: str = "Test MF"
) -> RawNavPlanDetailsResponse:
    return RawNavPlanDetailsResponse(
        sd_id=sd_id, fund_house=fund_house, scheme=scheme, plan=plan
    )


def _nav(sd_id: str, hnav_date: str, hnav_amt: str = "10.0") -> RawNavResponse:
    return RawNavResponse.from_dict(
        {
            "SD_ID": sd_id,
            "NAV_Name": "Plan",
            "hNAV_Amt": hnav_amt,
            "ISIN_RI": "",
            "ISIN_PO": "",
            "hNAV_Date": hnav_date,
            "hNAV_Dtstamp": f"{hnav_date}T00:00:00Z",
            "hNAV_reissue": "",
            "hNAV_repurchase": "",
            "hNAV_Upload_display": "01 Jan 2024 00:00:00",
        }
    )


def test_build_on_empty_database_produces_empty_derived(tmp_path: Path) -> None:
    """Full pipeline must execute cleanly even when every raw table is empty."""
    db = Database(db_path=str(tmp_path / "empty.duckdb"))
    try:
        _init_db(db)
        db.build()
        for cls in DERIVED_OBJECTS:
            row = db.conn.execute(f"SELECT COUNT(*) FROM {cls.name()}").fetchone()
            assert row is not None and row[0] == 0
    finally:
        db.close()


def test_build_end_to_end_with_synthetic_fund(tmp_path: Path) -> None:
    """Seed just enough raw data to produce one row through plans + nav."""
    db = Database(db_path=str(tmp_path / "e2e.duckdb"))
    try:
        _init_db(db)

        db.insert_fund_houses([_fh("1", "Test MF")])

        db.conn.execute(
            """
            INSERT INTO raw_scheme (
                mf_id, mf_name, scheme_id, scheme_name, scheme_objective,
                scheme_type_desc, scheme_cat_desc, launch_date, scheme_load,
                scheme_min_amt, amc_website
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                "1",
                "Test MF",
                "100",
                "Equity Scheme",
                "obj",
                "Open Ended",
                "Equity - Large Cap Fund",
                "2020-01-01",
                "",
                "",
                "",
            ],
        )

        db.insert_or_ignore_nav_plan_details(
            [
                _npd(
                    "500",
                    "Equity Scheme",
                    "Equity Scheme - Direct Plan - Growth",
                )
            ]
        )

        import datetime as dt

        today = dt.date.today()
        db.bulk_insert_nav(
            [
                _nav("500", "2020-01-01", "10.0"),
                _nav("500", today.isoformat(), "20.0"),
            ]
        )

        db.build()

        plans_active = db.conn.execute(
            "SELECT fund_house, scheme, plan, category, is_growth, is_direct "
            "FROM plans_active_v"
        ).fetchall()
        assert len(plans_active) == 1
        fh, scheme, plan, category, is_growth, is_direct = plans_active[0]
        assert fh == "Test MF"
        assert scheme == "Equity Scheme"
        assert category == "equity"
        assert is_growth is True
        assert is_direct is True

        plans_row = db.conn.execute("SELECT sd_id, scheme, tax FROM plans").fetchone()
        assert plans_row is not None
        assert plans_row[0] == 500
        assert float(plans_row[2]) == 0.125  # equity LTCG rate

        nav_rows = db.conn.execute("SELECT COUNT(*) FROM nav").fetchone()
        assert nav_rows is not None and nav_rows[0] == 2
    finally:
        db.close()


def test_derived_mro_contains_expected_protocol() -> None:
    """Static hierarchy check (Protocols aren't runtime_checkable)."""
    for view_cls in (PlansActiveView, NavActiveView):
        assert DerivedView in view_cls.__mro__
    for table_cls in (TaxCategoryTable, PlansFundsTable, NavFundsTable):
        assert DerivedTable in table_cls.__mro__
    for view_cls2 in (PlansView, NavView):
        assert DerivedView in view_cls2.__mro__


def test_build_is_idempotent(tmp_path: Path) -> None:
    db = Database(db_path=str(tmp_path / "idem.duckdb"))
    try:
        _init_db(db)
        db.build()
        db.build()  # should not raise on existing views/tables
    finally:
        db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
