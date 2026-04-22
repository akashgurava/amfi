from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from amfi.data import (
    RawFundHouse,
    RawFundHouseResponse,
    RawNavPlanDetails,
    RawNavPlanDetailsResponse,
    RawNavResponse,
)
from amfi.db import Database


def _fund_house(mf_id: str = "1", mf_name: str = "Test MF") -> RawFundHouseResponse:
    return RawFundHouseResponse.from_dict(
        {"mf_id": mf_id, "mf_name": mf_name, "amc_name": "Test AMC"}
    )


def _nav(sd_id: str, hnav_date: str) -> RawNavResponse:
    return RawNavResponse.from_dict(
        {
            "SD_ID": sd_id,
            "NAV_Name": "Plan A",
            "hNAV_Amt": "10.0",
            "ISIN_RI": "",
            "ISIN_PO": "",
            "hNAV_Date": hnav_date,
            "hNAV_Dtstamp": "",
            "hNAV_reissue": "",
            "hNAV_repurchase": "",
            "hNAV_Upload_display": "",
        }
    )


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(db_path=str(tmp_path / "test.duckdb"))


def test_create_raw_creates_all_tables(db: Database) -> None:
    db.create_raw()
    names = {
        r[0]
        for r in db.conn.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    assert {
        "raw_fund_house",
        "raw_scheme",
        "raw_scheme_document",
        "raw_scheme_aum",
        "raw_nav",
        "raw_nav_plan_details",
    }.issubset(names)


def test_insert_fund_houses_persists_rows(db: Database) -> None:
    db.create_raw()
    db.insert_fund_houses([_fund_house("1"), _fund_house("2", "Second")])

    ids = db.get_existing_raw_table_ids(RawFundHouse)
    assert sorted(ids) == ["1", "2"]


def test_insert_rejects_wrong_dataclass_type(db: Database) -> None:
    db.create_raw()
    nav = _nav("1", "2024-01-01")
    with pytest.raises(TypeError, match="Expected row type"):
        db.insert(RawFundHouse, nav)


def test_bulk_insert_nav_appends_without_dedup(db: Database) -> None:
    db.create_raw()
    db.bulk_insert_nav([_nav("1", "2024-01-01"), _nav("1", "2024-01-01")])
    row = db.conn.execute("SELECT COUNT(*) FROM raw_nav").fetchone()
    assert row is not None and row[0] == 2


def test_bulk_insert_nav_noop_on_empty(db: Database) -> None:
    db.create_raw()
    db.bulk_insert_nav([])
    row = db.conn.execute("SELECT COUNT(*) FROM raw_nav").fetchone()
    assert row is not None and row[0] == 0


def test_insert_or_ignore_nav_plan_details_skips_duplicates(db: Database) -> None:
    db.create_raw()
    row = RawNavPlanDetailsResponse(sd_id="10", fund_house="FH", scheme="S", plan="P")
    db.insert_or_ignore_nav_plan_details([row, row])
    count_row = db.conn.execute("SELECT COUNT(*) FROM raw_nav_plan_details").fetchone()
    assert count_row is not None and count_row[0] == 1


def test_get_missing_nav_dates_excludes_populated_dates(db: Database) -> None:
    db.create_raw()
    db.bulk_insert_nav([_nav("1", "2010-01-01"), _nav("2", "2010-01-03")])

    missing = db.get_missing_nav_dates()
    assert date(2010, 1, 1) not in missing
    assert date(2010, 1, 3) not in missing
    assert date(2010, 1, 2) in missing


def test_get_existing_raw_table_ids_for_nav_plan_details(db: Database) -> None:
    db.create_raw()
    db.insert_or_ignore_nav_plan_details(
        [RawNavPlanDetailsResponse("9", "FH", "S", "P")]
    )
    assert db.get_existing_raw_table_ids(RawNavPlanDetails) == ["9"]


def test_create_views_succeeds_on_valid_raw_data(db: Database) -> None:
    db.create_raw()
    db.insert_fund_houses([_fund_house("1")])
    db.create_views()
    row = db.conn.execute(
        "SELECT fund_house_id, fund_house FROM fund_house_v"
    ).fetchone()
    assert row == (1, "Test MF")


def test_create_views_raises_on_pre_check_failure(db: Database) -> None:
    from amfi.error import DataValidationError

    db.create_raw()
    # Insert row with non-numeric mf_id by bypassing dataclass validation
    db.conn.execute(
        "INSERT INTO raw_fund_house (mf_id, mf_name, amc_name) VALUES (?, ?, ?)",
        ["abc", "MF", "AMC"],
    )
    with pytest.raises(DataValidationError):
        db.create_views()


def test_close_disconnects(db: Database) -> None:
    db.create_raw()
    db.close()
