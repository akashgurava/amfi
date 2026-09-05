"""Raw database tables for AMFI portal data."""

from __future__ import annotations

from typing import Any

from ..core.base import RawTable
from .models import (
    RawFundHouseResponse,
    RawNavPlanDetailsResponse,
    RawNavResponse,
    RawSchemeAumResponse,
    RawSchemeDocumentResponse,
    RawSchemeResponse,
)


class RawFundHouse(RawTable[RawFundHouseResponse]):
    """Raw table for fund house data."""

    @classmethod
    def name(cls) -> str:
        return "raw_fund_house"

    @classmethod
    def row_type(cls) -> type[RawFundHouseResponse]:
        return RawFundHouseResponse

    @classmethod
    def column_definitions(cls) -> str:
        return """
                mf_id TEXT NOT NULL,
                mf_name TEXT NOT NULL,
                amc_name TEXT NOT NULL,
                amc_website TEXT,
                amc_schemewise_annual_report TEXT,
                amc_fortnightly_portfolio_disclosure TEXT,
                amc_monthly_portfolio_disclosure TEXT,
                amc_halfYearly_portfolio_disclosure TEXT,
                amc_monthly_mf_factsheets TEXT,
                amc_riskometer_monthly TEXT,
                amc_riskometer_yearly TEXT,
                amc_unclaimed_dividend_amt TEXT,
                amc_unclaimed_redemption_amt TEXT,
                amc_investonline_in_mf TEXT,
                rss_latest_nav TEXT,
                rss_latest_aum TEXT,
                statement_of_information TEXT,
                scheme_wise TEXT,
                icon_wordmark TEXT,
                icons TEXT,
            """

    @classmethod
    def insert_columns(cls) -> tuple[str, ...]:
        return (
            "mf_id",
            "mf_name",
            "amc_name",
            "amc_website",
            "amc_schemewise_annual_report",
            "amc_fortnightly_portfolio_disclosure",
            "amc_monthly_portfolio_disclosure",
            "amc_halfYearly_portfolio_disclosure",
            "amc_monthly_mf_factsheets",
            "amc_riskometer_monthly",
            "amc_riskometer_yearly",
            "amc_unclaimed_dividend_amt",
            "amc_unclaimed_redemption_amt",
            "amc_investonline_in_mf",
            "rss_latest_nav",
            "rss_latest_aum",
            "statement_of_information",
            "scheme_wise",
            "icon_wordmark",
            "icons",
        )

    @classmethod
    def id_columns(cls) -> tuple[str]:
        return ("mf_id",)


class RawScheme(RawTable[RawSchemeResponse]):
    """Raw table for scheme data."""

    @classmethod
    def name(cls) -> str:
        return "raw_scheme"

    @classmethod
    def row_type(cls) -> type[RawSchemeResponse]:
        return RawSchemeResponse

    @classmethod
    def column_definitions(cls) -> str:
        return """
                mf_id TEXT NOT NULL,
                mf_name TEXT NOT NULL,
                scheme_id TEXT NOT NULL,
                scheme_name TEXT NOT NULL,
                scheme_objective TEXT,
                scheme_type_desc TEXT,
                scheme_cat_desc TEXT,
                launch_date TEXT,
                scheme_load TEXT,
                scheme_min_amt TEXT,
                amc_website TEXT,
            """

    @classmethod
    def insert_columns(cls) -> tuple[str, ...]:
        return (
            "mf_id",
            "mf_name",
            "scheme_id",
            "scheme_name",
            "scheme_objective",
            "scheme_type_desc",
            "scheme_cat_desc",
            "launch_date",
            "scheme_load",
            "scheme_min_amt",
            "amc_website",
        )

    @classmethod
    def id_columns(cls) -> tuple[str]:
        return ("scheme_id",)


class RawSchemeDocument(RawTable[RawSchemeDocumentResponse]):
    """Raw table for scheme document data."""

    @classmethod
    def name(cls) -> str:
        return "raw_scheme_document"

    @classmethod
    def row_type(cls) -> type[RawSchemeDocumentResponse]:
        return RawSchemeDocumentResponse

    @classmethod
    def column_definitions(cls) -> str:
        return """
                scheme_id TEXT NOT NULL,
                info_document_url TEXT,
                summary_pdf_url TEXT,
                summary_xls_url TEXT,
                summary_xml_url TEXT,
            """

    @classmethod
    def insert_columns(cls) -> tuple[str, ...]:
        return (
            "scheme_id",
            "info_document_url",
            "summary_pdf_url",
            "summary_xls_url",
            "summary_xml_url",
        )

    @classmethod
    def id_columns(cls) -> tuple[str]:
        return ("scheme_id",)


class RawSchemeAum(RawTable[RawSchemeAumResponse]):
    """Raw table for scheme AUM data."""

    @classmethod
    def name(cls) -> str:
        return "raw_scheme_aum"

    @classmethod
    def row_type(cls) -> type[RawSchemeAumResponse]:
        return RawSchemeAumResponse

    @classmethod
    def column_definitions(cls) -> str:
        return """
                str_mf_id TEXT,
                str_sd_id TEXT NOT NULL,
                scheme_nav_name TEXT,
                average_aum_for_the_quarter TEXT,
                as_at_the_end_of TEXT,
                str_option TEXT,
            """

    @classmethod
    def insert_columns(cls) -> tuple[str, ...]:
        return (
            "str_mf_id",
            "str_sd_id",
            "scheme_nav_name",
            "average_aum_for_the_quarter",
            "as_at_the_end_of",
            "str_option",
        )

    @classmethod
    def id_columns(cls) -> tuple[str]:
        return ("str_sd_id",)


class RawNavPlanDetails(RawTable[RawNavPlanDetailsResponse]):
    """Raw table for NAV plan details data."""

    @classmethod
    def name(cls) -> str:
        return "raw_nav_plan_details"

    @classmethod
    def row_type(cls) -> type[RawNavPlanDetailsResponse]:
        return RawNavPlanDetailsResponse

    @classmethod
    def column_definitions(cls) -> str:
        return """
                sd_id TEXT NOT NULL PRIMARY KEY,
                fund_house TEXT NOT NULL,
                scheme TEXT NOT NULL,
                plan TEXT NOT NULL,
            """

    @classmethod
    def insert_columns(cls) -> tuple[str, ...]:
        return (
            "sd_id",
            "fund_house",
            "scheme",
            "plan",
        )

    @classmethod
    def insert_sql(cls) -> str:
        columns = cls.insert_columns()
        placeholders = ", ".join(["?"] * len(columns))
        columns_sql = ", ".join(columns)
        return (
            f"INSERT INTO {cls.name()} ({columns_sql}) VALUES ({placeholders})"
            " ON CONFLICT (sd_id) DO NOTHING"
        )

    @classmethod
    def id_columns(cls) -> tuple[str]:
        return ("sd_id",)


class RawNav(RawTable[RawNavResponse]):
    """Raw table for NAV data."""

    @classmethod
    def name(cls) -> str:
        return "raw_nav"

    @classmethod
    def row_type(cls) -> type[RawNavResponse]:
        return RawNavResponse

    @classmethod
    def column_definitions(cls) -> str:
        return """
                sd_id TEXT NOT NULL,
                nav_name TEXT NOT NULL,
                hnav_amt TEXT,
                isin_ri TEXT,
                isin_po TEXT,
                hnav_date TEXT,
                hnav_dtstamp TEXT,
                hnav_reissue TEXT,
                hnav_repurchase TEXT,
                hnav_upload_display TEXT,
            """

    @classmethod
    def insert_columns(cls) -> tuple[str, ...]:
        return (
            "sd_id",
            "nav_name",
            "hnav_amt",
            "isin_ri",
            "isin_po",
            "hnav_date",
            "hnav_dtstamp",
            "hnav_reissue",
            "hnav_repurchase",
            "hnav_upload_display",
        )


PORTAL_RAW_TABLES: tuple[type[RawTable[Any]], ...] = (
    RawFundHouse,
    RawScheme,
    RawSchemeDocument,
    RawSchemeAum,
    RawNav,
    RawNavPlanDetails,
)
