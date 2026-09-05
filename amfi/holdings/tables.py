"""Raw database tables for AMC portfolio statements and holdings."""

from __future__ import annotations

from typing import Any

from ..core.base import Table


class RawAmcMasterAbsl(Table):
    """Mapping table from ABSL sheet names to AMFI scheme_id."""

    @classmethod
    def name(cls) -> str:
        return "raw_amc_master_absl"

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        prefix = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE OR REPLACE TABLE"
        return f"""
        CREATE SEQUENCE IF NOT EXISTS seq_raw_amc_master_absl START 1;
        {prefix} {cls.name()} (
            amc_scheme_id INTEGER PRIMARY KEY DEFAULT nextval('seq_raw_amc_master_absl'),
            amc_sheet_name VARCHAR NOT NULL,
            amc_scheme_name VARCHAR NOT NULL,
            scheme_id INTEGER,
            last_statement_date DATE,
            insert_ts TIMESTAMP DEFAULT current_timestamp,
            UNIQUE (amc_sheet_name)
        );
        """


class RawHoldingSections(Table):
    """Normalized holding sections lookup table."""

    @classmethod
    def name(cls) -> str:
        return "raw_holding_sections"

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        prefix = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE OR REPLACE TABLE"
        return f"""
        CREATE SEQUENCE IF NOT EXISTS seq_raw_holding_sections START 1;
        {prefix} {cls.name()} (
            section_id UTINYINT PRIMARY KEY DEFAULT nextval('seq_raw_holding_sections'),
            section_name VARCHAR NOT NULL,
            broad_category VARCHAR NOT NULL,
            insert_ts TIMESTAMP DEFAULT current_timestamp,
            UNIQUE (section_name)
        );
        """


class RawInstrumentMaster(Table):
    """Normalized instrument master lookup table."""

    @classmethod
    def name(cls) -> str:
        return "raw_instrument_master"

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        prefix = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE OR REPLACE TABLE"
        return f"""
        CREATE SEQUENCE IF NOT EXISTS seq_raw_instrument_master START 1;
        {prefix} {cls.name()} (
            instrument_id INTEGER PRIMARY KEY DEFAULT nextval('seq_raw_instrument_master'),
            instrument_name VARCHAR NOT NULL,
            isin VARCHAR,
            industry_or_rating VARCHAR,
            insert_ts TIMESTAMP DEFAULT current_timestamp,
            UNIQUE (instrument_name, isin, industry_or_rating)
        );
        """


class RawPortfolioStatement(Table):
    """Header table for a scheme's monthly or fortnightly portfolio statement."""

    @classmethod
    def name(cls) -> str:
        return "raw_portfolio_statement"

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        prefix = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE OR REPLACE TABLE"
        return f"""
        CREATE SEQUENCE IF NOT EXISTS seq_raw_portfolio_statement START 1;
        {prefix} {cls.name()} (
            statement_id INTEGER PRIMARY KEY DEFAULT nextval('seq_raw_portfolio_statement'),
            fund_house_id INTEGER NOT NULL,
            scheme_id INTEGER NOT NULL,
            portfolio_date DATE NOT NULL,
            frequency VARCHAR NOT NULL,
            total_aum_lakhs DOUBLE,
            holding_count INTEGER DEFAULT 0,
            rejected_count INTEGER DEFAULT 0,
            source_file VARCHAR,
            insert_ts TIMESTAMP DEFAULT current_timestamp,
            UNIQUE (scheme_id, portfolio_date, frequency)
        );
        """


class RawSchemeHoldings(Table):
    """Quantitative holding rows referencing statements and instrument master."""

    @classmethod
    def name(cls) -> str:
        return "raw_scheme_holdings"

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        prefix = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE OR REPLACE TABLE"
        return f"""
        CREATE SEQUENCE IF NOT EXISTS seq_raw_scheme_holdings START 1;
        {prefix} {cls.name()} (
            holding_id BIGINT PRIMARY KEY DEFAULT nextval('seq_raw_scheme_holdings'),
            statement_id INTEGER NOT NULL,
            section_id UTINYINT NOT NULL,
            instrument_id INTEGER NOT NULL,
            quantity DOUBLE,
            market_value_lakhs DOUBLE NOT NULL,
            aum_pct DOUBLE NOT NULL,
            ytm_pct DOUBLE,
            ytc_pct DOUBLE,
            insert_ts TIMESTAMP DEFAULT current_timestamp
        );
        """


class RawRejectedAmcHoldings(Table):
    """Audit log for rows that failed validation rules during statement ingestion."""

    @classmethod
    def name(cls) -> str:
        return "raw_rejected_amc_holdings"

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        prefix = "CREATE TABLE IF NOT EXISTS" if if_not_exists else "CREATE OR REPLACE TABLE"
        return f"""
        CREATE SEQUENCE IF NOT EXISTS seq_raw_rejected_amc_holdings START 1;
        {prefix} {cls.name()} (
            rejection_id BIGINT PRIMARY KEY DEFAULT nextval('seq_raw_rejected_amc_holdings'),
            amc VARCHAR NOT NULL,
            scheme VARCHAR,
            sheet_name VARCHAR,
            line_number INTEGER,
            raw_row VARCHAR,
            reason VARCHAR NOT NULL,
            full_reason VARCHAR,
            insert_ts TIMESTAMP DEFAULT current_timestamp
        );
        """


HOLDINGS_TABLES: tuple[type[Table], ...] = (
    RawAmcMasterAbsl,
    RawHoldingSections,
    RawInstrumentMaster,
    RawPortfolioStatement,
    RawSchemeHoldings,
    RawRejectedAmcHoldings,
)
