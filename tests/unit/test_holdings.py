"""Unit tests for AMC portfolio scrapers, validators, and database persistence."""

from datetime import date

import duckdb
import pytest

from amfi.holdings import (
    AbslPortfolioScraper,
    BroadAssetCategory,
    DisclosureFrequency,
    DisclosureMeta,
    HoldingCandidate,
    HoldingsRepository,
    RowValidator,
    StatementMeta,
    categorize_section,
    normalize_scheme_name,
)
from amfi.holdings.amc.absl import canonicalize_absl_url, parse_disclosure_date_from_title


def test_validator_valid_row() -> None:
    validator = RowValidator(amc_name="ABSL", scheme_name="Flexi Cap Fund")
    cand = HoldingCandidate(
        sheet_name="BSLEQTY",
        line_number=10,
        raw_row=["", "ICICI Bank Ltd.", "INE090A01021", "Banks", 1000, 150000.0, 0.0534],
        section_name="Equity & Equity Related",
        instrument_name="ICICI Bank Ltd.",
        isin="INE090A01021",
        industry_or_rating="Banks",
        quantity=1000,
        market_value_lakhs=150000.0,
        aum_pct=0.0534,
        ytm_pct=None,
        ytc_pct=None,
    )

    validated, rejection = validator.validate(cand)
    assert rejection is None
    assert validated is not None
    assert validated.instrument_name == "ICICI Bank Ltd."
    assert validated.isin == "INE090A01021"
    assert validated.market_value_lakhs == 150000.0
    assert validated.aum_pct == 5.34
    assert validated.broad_category == BroadAssetCategory.EQUITY


def test_validator_cash_item_without_isin() -> None:
    validator = RowValidator(amc_name="ABSL", scheme_name="Flexi Cap Fund")
    cand = HoldingCandidate(
        sheet_name="BSLEQTY",
        line_number=98,
        raw_row=["", "TREPS", "", "", "", 8598.51, 0.0031],
        section_name="TREPS / Reverse Repo Investments",
        instrument_name="TREPS",
        isin="",
        industry_or_rating=None,
        quantity=None,
        market_value_lakhs=8598.51,
        aum_pct=0.0031,
    )

    validated, rejection = validator.validate(cand)
    assert rejection is None
    assert validated is not None
    assert validated.isin is None
    assert validated.quantity is None
    assert validated.market_value_lakhs == 8598.51
    assert validated.broad_category == BroadAssetCategory.CASH


def test_validator_negative_market_value_and_aum_pct() -> None:
    validator = RowValidator(amc_name="ABSL", scheme_name="Liquid Fund")
    cand = HoldingCandidate(
        sheet_name="PLUS",
        line_number=105,
        raw_row=["", "Net Receivable / Payable", "", "", "", -82060.23, -0.0828],
        section_name="Cash & Cash Receivables",
        instrument_name="Net Receivable / Payable",
        isin=None,
        industry_or_rating=None,
        quantity=None,
        market_value_lakhs=-82060.23,
        aum_pct=-0.0828,
    )

    validated, rejection = validator.validate(cand)
    assert rejection is None
    assert validated is not None
    assert validated.market_value_lakhs == -82060.23
    assert validated.aum_pct == -8.28


def test_validator_micro_holdings_dollar_pct() -> None:
    validator = RowValidator(amc_name="ABSL", scheme_name="Flexi Cap Fund")
    cand = HoldingCandidate(
        sheet_name="BSLEQTY",
        line_number=88,
        raw_row=["", "Globsyn Technologies Ltd", "INE671B01034", "Miscellaneous", 20000, 0.0, "$0.00%"],
        section_name="Equity & Equity Related",
        instrument_name="Globsyn Technologies Ltd",
        isin="INE671B01034",
        industry_or_rating="Miscellaneous",
        quantity=20000,
        market_value_lakhs=0.0,
        aum_pct="$0.00%",
    )

    validated, rejection = validator.validate(cand)
    assert rejection is None
    assert validated is not None
    assert validated.market_value_lakhs == 0.0
    assert validated.aum_pct == 0.0


def test_validator_rejection_missing_market_value() -> None:
    validator = RowValidator(amc_name="ABSL", scheme_name="Flexi Cap Fund")
    cand = HoldingCandidate(
        sheet_name="BSLEQTY",
        line_number=45,
        raw_row=["", "Test Company", "INE123A01010", "IT", 100, "-", 0.02],
        section_name="Equity",
        instrument_name="Test Company",
        isin="INE123A01010",
        industry_or_rating="IT",
        quantity=100,
        market_value_lakhs="-",
        aum_pct=0.02,
    )

    validated, rejection = validator.validate(cand)
    assert validated is None
    assert rejection is not None
    assert rejection.line_number == 45
    assert "market_value_lakhs" in rejection.reason
    assert "Test Company" in rejection.raw_row


def test_validator_rejection_invalid_isin() -> None:
    validator = RowValidator(amc_name="ABSL", scheme_name="Flexi Cap Fund")
    cand = HoldingCandidate(
        sheet_name="BSLEQTY",
        line_number=46,
        raw_row=["", "Test Company", "INVALID_ISIN", "IT", 100, 500.0, 0.02],
        section_name="Equity",
        instrument_name="Test Company",
        isin="INVALID_ISIN",
        industry_or_rating="IT",
        quantity=100,
        market_value_lakhs=500.0,
        aum_pct=0.02,
    )

    validated, rejection = validator.validate(cand)
    assert validated is None
    assert rejection is not None
    assert rejection.reason == "Invalid ISIN format"


def test_categorize_section() -> None:
    assert categorize_section("Equity & Equity Related") == BroadAssetCategory.EQUITY
    assert categorize_section("Listed/awaiting listing on Stock Exchanges") == BroadAssetCategory.EQUITY
    assert categorize_section("Government Securities (G-Sec)") == BroadAssetCategory.DEBT
    assert categorize_section("Commercial Paper (CP)") == BroadAssetCategory.DEBT
    assert categorize_section("TREPS / Reverse Repo Investments") == BroadAssetCategory.CASH
    assert categorize_section("Silver ETF") == BroadAssetCategory.COMMODITY
    assert categorize_section("Interest Rate Swaps (IRS)") == BroadAssetCategory.DERIVATIVE
    assert categorize_section("Miscellaneous Unknown") == BroadAssetCategory.OTHER


def test_parse_disclosure_date_from_title() -> None:
    assert parse_disclosure_date_from_title("Monthly Portfolios as on July 31, 2026") == date(2026, 7, 31)
    assert parse_disclosure_date_from_title("Monthly Portfolio 30 June 2026") == date(2026, 6, 30)
    assert parse_disclosure_date_from_title("31052026_abslmf_monthly-portfolio.zip") == date(2026, 5, 31)
    assert parse_disclosure_date_from_title("Monthly Disclosure-April-30-2026.zip") == date(2026, 4, 30)
    assert parse_disclosure_date_from_title("SEBI_Monthly_Portfolio 31 JAN 2026.xls") == date(2026, 1, 31)
    assert parse_disclosure_date_from_title("sebi_monthly_portfolio-31-oct-2025-2-1.zip") == date(2025, 10, 31)


def test_canonicalize_absl_url() -> None:
    cdn_url = "https://abcscprod.azureedge.net/-/media/bsl/files/resources/monthly-portfolio/2026/test.zip"
    expected = "https://mutualfund.adityabirlacapital.com/-/media/bsl/files/resources/monthly-portfolio/2026/test.zip"
    assert canonicalize_absl_url(cdn_url) == expected


def test_normalize_scheme_name() -> None:
    assert normalize_scheme_name("ADITYA BIRLA SUN LIFE FLEXI CAP FUND") == "FLEXICAPFUND"
    assert normalize_scheme_name("Aditya Birla Sun Life Pharma & Healthcare Fund") == "PHARMAANDHEALTHCAREFUND"
    assert normalize_scheme_name("ADITYA BIRLA SUN LIFE SILVER ETF FUND OF FUND") == "SILVERETFFOF"
    assert normalize_scheme_name("US TREASURY 1-3 YEAR BONDS ETFS PASSIVE FOF") == "USTREASURY13YEARBONDETFSPASSIVEFOF"
    assert normalize_scheme_name("CRISIL IBX GILT APR 2033 INDEX FUND") == "CRISILIBXGILTAPRIL2033INDEXFUND"


def test_database_persistence_and_views() -> None:
    from amfi.db import Database
    from amfi.holdings import HOLDINGS_TABLES

    db_instance = Database(":memory:")
    for table in HOLDINGS_TABLES:
        db_instance._execute(table.create_sql(), operation="INIT_TEST_TABLES")
    conn = db_instance.conn
    repo = HoldingsRepository(conn)

    # 1. Test section creation and deduplication
    s1 = repo.get_or_create_section_id("Equity", "Equity")
    s2 = repo.get_or_create_section_id("Equity", "Equity")
    assert s1 == s2

    # 2. Test instrument creation and deduplication
    i1 = repo.get_or_create_instrument_id("HDFC Bank Ltd.", "INE040A01034", "Banks")
    i2 = repo.get_or_create_instrument_id("HDFC Bank Ltd.", "INE040A01034", "Banks")
    assert i1 == i2

    # 3. Test saving statement with holdings and rejections
    stmt = StatementMeta(
        fund_house_id=3,
        scheme_id=4390,
        amc_sheet_name="BSLEQTY",
        amc_scheme_name="Aditya Birla Sun Life Flexi Cap Fund",
        portfolio_date=date(2026, 7, 31),
        frequency=DisclosureFrequency.MONTHLY,
        total_aum_lakhs=2811233.43,
        source_file="test.zip",
    )

    validator = RowValidator(amc_name="ABSL", scheme_name="Flexi Cap Fund")
    # Valid row
    h1, _ = validator.validate(
        HoldingCandidate(
            sheet_name="BSLEQTY",
            line_number=7,
            raw_row=["", "ICICI Bank Ltd.", "INE090A01021", "Banks", 1000, 170083.0, 0.0605],
            section_name="Equity",
            instrument_name="ICICI Bank Ltd.",
            isin="INE090A01021",
            industry_or_rating="Banks",
            quantity=1000,
            market_value_lakhs=170083.0,
            aum_pct=0.0605,
        )
    )
    stmt.holdings.append(h1)

    # Invalid row
    _, rej = validator.validate(
        HoldingCandidate(
            sheet_name="BSLEQTY",
            line_number=8,
            raw_row=["", "Invalid Co", "BAD_ISIN", "IT", 10, 50.0, 0.01],
            section_name="Equity",
            instrument_name="Invalid Co",
            isin="BAD_ISIN",
            industry_or_rating="IT",
            quantity=10,
            market_value_lakhs=50.0,
            aum_pct=0.01,
        )
    )
    stmt.rejections.append(rej)

    statement_id = repo.save_statement(stmt)
    assert statement_id > 0

    # Verify tables
    holdings_count = conn.execute("SELECT COUNT(*) FROM raw_scheme_holdings").fetchone()[0]
    assert holdings_count == 1

    rej_count = conn.execute("SELECT COUNT(*) FROM raw_rejected_amc_holdings").fetchone()[0]
    assert rej_count == 1

    # Verify AMC master upsert
    repo.upsert_amc_master_absl("BSLEQTY", "Flexi Cap Fund", 4390, date(2026, 7, 31))
    master_row = conn.execute("SELECT * FROM raw_amc_master_absl WHERE amc_sheet_name = 'BSLEQTY'").fetchone()
    assert master_row is not None
    assert master_row[1] == "BSLEQTY"
    assert master_row[3] == 4390
