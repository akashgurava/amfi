"""Unit tests for AMFI ETL module."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from amfi.etl import (
    _extract_idcw_frequency,
    _extract_option_type,
    _extract_plan_type,
    flatten_json,
    run_etl_pipeline,
)


def _nav_record(sd_id: str, name: str, amt: str) -> dict:
    """Helper to create a minimal NAV record for tests."""
    return {
        "SD_ID": sd_id,
        "NAV_Name": name,
        "hNAV_Amt": amt,
        "ISIN_PO": "",
        "ISIN_RI": "",
        "hNAV_Date": "",
        "hNAV_Dtstamp": "",
        "hNAV_reissue": "",
        "hNAV_repurchase": "",
        "hNAV_Upload_display": "",
    }


class TestExtractPlanType:
    def test_direct_plan(self):
        result = _extract_plan_type("HDFC Equity Fund - Direct Plan - Growth")
        assert result == "Direct"

    def test_regular_plan(self):
        result = _extract_plan_type("HDFC Equity Fund - Regular Plan - Growth")
        assert result == "Regular"

    def test_retail_plan(self):
        result = _extract_plan_type("SBI Blue Chip Fund - retail - Growth")
        assert result == "Retail"

    def test_institutional_plan(self):
        result = _extract_plan_type("ICICI Pru Fund - Institutional - Growth")
        assert result == "Institutional"

    def test_unknown_plan(self):
        assert _extract_plan_type("Some Fund - Growth") is None


class TestExtractOptionType:
    def test_growth_option(self):
        assert _extract_option_type("HDFC Equity Fund - Direct - Growth") == "Growth"

    def test_idcw_option(self):
        assert _extract_option_type("HDFC Equity Fund - Direct - IDCW") == "IDCW"

    def test_dividend_option(self):
        assert _extract_option_type("HDFC Equity Fund - Direct - Dividend") == "IDCW"

    def test_bonus_option(self):
        assert _extract_option_type("HDFC Equity Fund - Direct - Bonus") == "Bonus"

    def test_unknown_option(self):
        assert _extract_option_type("HDFC Equity Fund - Direct") is None


class TestExtractIdcwFrequency:
    def test_monthly(self):
        assert _extract_idcw_frequency("Fund - Monthly IDCW") == "Monthly"

    def test_quarterly(self):
        assert _extract_idcw_frequency("Fund - Quarterly Dividend") == "Quarterly"

    def test_half_yearly(self):
        assert _extract_idcw_frequency("Fund - Half Yearly IDCW") == "HalfYearly"

    def test_annual(self):
        assert _extract_idcw_frequency("Fund - Annual Dividend") == "Annual"

    def test_no_frequency(self):
        assert _extract_idcw_frequency("Fund - Growth") is None


class TestFlattenJson:
    def test_flatten_single_record(self, tmp_path: Path):
        data = {
            "data": [
                {
                    "mfName": "Test MF",
                    "schemes": [
                        {
                            "schemeName": "Test Scheme",
                            "navs": [
                                {
                                    "SD_ID": "12345",
                                    "NAV_Name": "Test Scheme - Direct - Growth",
                                    "hNAV_Amt": "100.5000",
                                    "ISIN_PO": "INF123456789",
                                    "ISIN_RI": "",
                                    "hNAV_Date": "2024-01-01T00:00:00.000Z",
                                    "hNAV_Dtstamp": "2024-01-01T20:00:00.000Z",
                                    "hNAV_reissue": "",
                                    "hNAV_repurchase": "",
                                    "hNAV_Upload_display": "01 Jan 2024 20:00:00",
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps(data))

        records = flatten_json(json_file)

        assert len(records) == 1
        record = records[0]
        assert record["sd_id"] == "12345"
        assert record["nav_name"] == "Test Scheme - Direct - Growth"
        assert record["hnav_amt"] == "100.5000"
        assert record["isin_po"] == "INF123456789"
        assert record["isin_ri"] == ""
        assert record["mf_name"] == "Test MF"
        assert record["scheme_name"] == "Test Scheme"
        assert record["plan_type"] == "Direct"
        assert record["option_type"] == "Growth"
        assert record["idcw_frequency"] is None
        assert record["_source_file"] == "test.json"

    def test_flatten_multiple_mfs_and_schemes(self, tmp_path: Path):
        data = {
            "data": [
                {
                    "mfName": "MF1",
                    "schemes": [
                        {
                            "schemeName": "Scheme1",
                            "navs": [_nav_record("1", "S1", "10")],
                        },
                        {
                            "schemeName": "Scheme2",
                            "navs": [_nav_record("2", "S2", "20")],
                        },
                    ],
                },
                {
                    "mfName": "MF2",
                    "schemes": [
                        {
                            "schemeName": "Scheme3",
                            "navs": [_nav_record("3", "S3", "30")],
                        },
                    ],
                },
            ]
        }

        json_file = tmp_path / "multi.json"
        json_file.write_text(json.dumps(data))

        records = flatten_json(json_file)

        assert len(records) == 3
        assert records[0]["mf_name"] == "MF1"
        assert records[0]["scheme_name"] == "Scheme1"
        assert records[1]["mf_name"] == "MF1"
        assert records[1]["scheme_name"] == "Scheme2"
        assert records[2]["mf_name"] == "MF2"
        assert records[2]["scheme_name"] == "Scheme3"


class TestETLPipeline:
    def test_full_pipeline(self, tmp_path: Path):
        data = {
            "data": [
                {
                    "mfName": "Test MF",
                    "schemes": [
                        {
                            "schemeName": "Test Scheme",
                            "navs": [
                                {
                                    "SD_ID": "12345",
                                    "NAV_Name": "Test Scheme - Direct - Growth",
                                    "hNAV_Amt": "100.5000",
                                    "ISIN_PO": "INF123456789",
                                    "ISIN_RI": "",
                                    "hNAV_Date": "2024-01-01T00:00:00.000Z",
                                    "hNAV_Dtstamp": "2024-01-01T20:00:00.000Z",
                                    "hNAV_reissue": "",
                                    "hNAV_repurchase": "",
                                    "hNAV_Upload_display": "01 Jan 2024 20:00:00",
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps(data))
        db_file = tmp_path / "test.duckdb"

        counts = run_etl_pipeline(db_file, [json_file])

        assert counts["bronze"] == 1
        assert counts["silver"] == 1
        assert counts["gold"] == 1

        conn = duckdb.connect(str(db_file))
        try:
            # Verify Bronze
            bronze = conn.execute("SELECT * FROM raw_nav").fetchall()
            assert len(bronze) == 1

            # Verify Silver
            silver = conn.execute("SELECT * FROM clean_nav").fetchall()
            assert len(silver) == 1

            # Verify Gold
            gold = conn.execute("SELECT * FROM nav_daily").fetchall()
            assert len(gold) == 1

            # Verify types in Silver
            silver_row = conn.execute(
                "SELECT sd_id, nav_amount, nav_date FROM clean_nav"
            ).fetchone()
            assert silver_row[0] == 12345  # INTEGER
            assert float(silver_row[1]) == 100.5  # DECIMAL
        finally:
            conn.close()

    def test_deduplication_in_gold(self, tmp_path: Path):
        """Test that Gold layer deduplicates by sd_id + nav_date."""
        data = {
            "data": [
                {
                    "mfName": "Test MF",
                    "schemes": [
                        {
                            "schemeName": "Test Scheme",
                            "navs": [
                                {
                                    "SD_ID": "12345",
                                    "NAV_Name": "Test Scheme - Direct - Growth",
                                    "hNAV_Amt": "100.0000",
                                    "ISIN_PO": "INF123456789",
                                    "ISIN_RI": "",
                                    "hNAV_Date": "2024-01-01T00:00:00.000Z",
                                    "hNAV_Dtstamp": "2024-01-01T18:00:00.000Z",
                                    "hNAV_reissue": "",
                                    "hNAV_repurchase": "",
                                    "hNAV_Upload_display": "01 Jan 2024 18:00:00",
                                },
                                {
                                    "SD_ID": "12345",
                                    "NAV_Name": "Test Scheme - Direct - Growth",
                                    "hNAV_Amt": "101.0000",
                                    "ISIN_PO": "INF123456789",
                                    "ISIN_RI": "",
                                    "hNAV_Date": "2024-01-01T00:00:00.000Z",
                                    "hNAV_Dtstamp": "2024-01-01T20:00:00.000Z",
                                    "hNAV_reissue": "",
                                    "hNAV_repurchase": "",
                                    "hNAV_Upload_display": "01 Jan 2024 20:00:00",
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        json_file = tmp_path / "dup.json"
        json_file.write_text(json.dumps(data))
        db_file = tmp_path / "dup.duckdb"

        counts = run_etl_pipeline(db_file, [json_file])

        assert counts["bronze"] == 2
        assert counts["silver"] == 2
        assert counts["gold"] == 1  # Deduplicated

        conn = duckdb.connect(str(db_file))
        try:
            gold_row = conn.execute(
                "SELECT nav_amount FROM nav_daily WHERE sd_id = 12345"
            ).fetchone()
            assert float(gold_row[0]) == 101.0  # Latest timestamp wins
        finally:
            conn.close()
