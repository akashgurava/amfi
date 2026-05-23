from __future__ import annotations

import pytest

from amfi.data import (
    RawFundHouse,
    RawFundHouseResponse,
    RawNav,
    RawNavPlanDetails,
    RawNavResponse,
    RawScheme,
    RawSchemeAum,
    RawSchemeDocument,
)
from amfi.data.raw import _as_str
from amfi.error import AppConfigError


def test_as_str_maps_none_to_empty_string() -> None:
    assert _as_str(None) == ""
    assert _as_str(42) == "42"
    assert _as_str("hello") == "hello"


def test_raw_fund_house_response_from_dict_handles_missing_keys() -> None:
    fh = RawFundHouseResponse.from_dict(
        {"mf_id": "10", "mf_name": "X", "amc_name": "Y"}
    )
    assert fh.mf_id == "10"
    assert fh.amc_website == ""


def test_raw_fund_house_response_validates_required_fields() -> None:
    with pytest.raises(ValueError, match="mf_id is required"):
        RawFundHouseResponse.from_dict({"mf_name": "X", "amc_name": "Y"})
    with pytest.raises(ValueError, match="mf_id must be a digit"):
        RawFundHouseResponse.from_dict(
            {"mf_id": "abc", "mf_name": "X", "amc_name": "Y"}
        )
    with pytest.raises(ValueError, match="mf_name is required"):
        RawFundHouseResponse.from_dict({"mf_id": "1", "amc_name": "Y"})
    with pytest.raises(ValueError, match="amc_name is required"):
        RawFundHouseResponse.from_dict({"mf_id": "1", "mf_name": "X"})


def test_raw_nav_response_from_dict_requires_sd_id_and_nav_name() -> None:
    with pytest.raises(ValueError, match="sd_id is required"):
        RawNavResponse.from_dict({"NAV_Name": "n"})
    with pytest.raises(ValueError, match="nav_name is required"):
        RawNavResponse.from_dict({"SD_ID": "123"})


def test_raw_nav_response_uses_api_camel_case_keys() -> None:
    resp = RawNavResponse.from_dict(
        {
            "SD_ID": "101",
            "NAV_Name": "Plan",
            "hNAV_Amt": "10.5",
            "ISIN_RI": "A",
            "ISIN_PO": "B",
            "hNAV_Date": "2024-01-01",
            "hNAV_Dtstamp": "2024-01-01T00:00:00Z",
            "hNAV_reissue": "",
            "hNAV_repurchase": "",
            "hNAV_Upload_display": "01 Jan 2024 00:00:00",
        }
    )
    assert resp.sd_id == "101"
    assert resp.hnav_amt == "10.5"
    assert resp.isin_ri == "A"
    assert resp.isin_po == "B"


def test_raw_table_create_rejects_conflicting_flags() -> None:
    with pytest.raises(AppConfigError):
        RawFundHouse.create_sql(if_not_exists=True, replace=True)


def test_raw_table_insert_sql_has_correct_placeholder_count() -> None:
    for table in (RawFundHouse, RawScheme, RawSchemeDocument, RawSchemeAum, RawNav):
        sql = table.insert_sql()
        assert sql.count("?") == len(table.insert_columns())
        assert table.name() in sql


def test_raw_nav_plan_details_insert_uses_on_conflict_do_nothing() -> None:
    sql = RawNavPlanDetails.insert_sql()
    assert "ON CONFLICT" in sql
    assert "DO NOTHING" in sql
    assert sql.count("?") == len(RawNavPlanDetails.insert_columns())


def test_raw_table_existing_id_sql_uses_distinct_id_columns() -> None:
    sql = RawNavPlanDetails.existing_id_sql()
    assert "DISTINCT" in sql
    assert "sd_id" in sql
    assert RawNavPlanDetails.name() in sql
