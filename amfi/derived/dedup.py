"""Deduplication views for AMFI portal raw tables."""

from typing import Any

from ..core.base import DerivedView, RawTable
from ..portal.tables import (
    RawFundHouse,
    RawNav,
    RawNavPlanDetails,
    RawScheme,
    RawSchemeAum,
    RawSchemeDocument,
)


class DedupView(DerivedView):
    """Base class for deduplication views."""

    @classmethod
    def source_table(cls) -> type[RawTable[Any]]:
        raise NotImplementedError

    @classmethod
    def id_columns(cls) -> tuple[str, ...]:
        raise NotImplementedError

    @classmethod
    def column_definitions(cls) -> str:
        raise NotImplementedError

    @classmethod
    def pre_check(cls) -> str | None:
        return None

    @classmethod
    def select_sql(cls) -> str:
        partition_by = ", ".join(cls.id_columns())
        return f"""
        SELECT {cls.column_definitions()}
        FROM {cls.source_table().name()}
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY {partition_by}
            ORDER BY loaded_at DESC
        ) = 1
        """


class FundHouseView(DedupView):
    """View for fund house data with deduplication."""

    @classmethod
    def name(cls) -> str:
        return "fund_house_v"

    @classmethod
    def source_table(cls) -> type[RawTable[Any]]:
        return RawFundHouse

    @classmethod
    def id_columns(cls) -> tuple[str, ...]:
        return ("mf_id",)

    @classmethod
    def pre_check(cls) -> str | None:
        return """
        WITH latest_data AS (
            SELECT mf_id, mf_name, amc_name
            FROM raw_fund_house
            QUALIFY ROW_NUMBER() OVER (PARTITION BY mf_id ORDER BY loaded_at DESC) = 1
        )
        SELECT 'mf_id' AS err_col, mf_id as err_val
        FROM latest_data
        WHERE TRY_CAST(mf_id AS INTEGER) IS NULL
        UNION ALL
        SELECT 'mf_name' AS err_col, mf_name as err_val
        FROM latest_data
        WHERE mf_name IS NULL OR mf_name = ''
        UNION ALL
        SELECT 'amc_name' AS err_col, amc_name as err_val
        FROM latest_data
        WHERE amc_name IS NULL OR amc_name = ''
        """

    @classmethod
    def column_definitions(cls) -> str:
        return """
        TRY_CAST(mf_id AS INTEGER) AS fund_house_id,
        mf_name AS fund_house,
        amc_name
        """


class SchemeView(DedupView):
    """View for scheme data with deduplication."""

    @classmethod
    def name(cls) -> str:
        return "scheme_v"

    @classmethod
    def source_table(cls) -> type[RawTable[Any]]:
        return RawScheme

    @classmethod
    def id_columns(cls) -> tuple[str, ...]:
        return ("scheme_id",)

    @classmethod
    def pre_check(cls) -> str | None:
        return """
        WITH latest_data AS (
            SELECT mf_id, mf_name, scheme_id, scheme_name,
                scheme_type_desc, scheme_cat_desc, launch_date,
                scheme_load, scheme_min_amt
            FROM raw_scheme
            QUALIFY ROW_NUMBER()
                OVER (PARTITION BY scheme_id ORDER BY loaded_at DESC) = 1
        )
        SELECT 'mf_id' AS err_col, mf_id as err_val
        FROM latest_data
        WHERE TRY_CAST(mf_id AS INTEGER) IS NULL
        UNION ALL
        SELECT 'mf_name' AS err_col, mf_name as err_val
        FROM latest_data
        WHERE mf_name IS NULL OR mf_name = ''
        UNION ALL
        SELECT 'scheme_id' AS err_col, scheme_id as err_val
        FROM latest_data
        WHERE TRY_CAST(scheme_id AS INTEGER) IS NULL
        UNION ALL
        SELECT 'scheme_name' AS err_col, scheme_name as err_val
        FROM latest_data
        WHERE scheme_name IS NULL OR scheme_name = ''
        UNION ALL
        SELECT 'scheme_type_desc' AS err_col, scheme_type_desc as err_val
        FROM latest_data
        WHERE scheme_type_desc IS NULL OR scheme_type_desc = ''
        UNION ALL
        SELECT 'scheme_cat_desc' AS err_col, scheme_cat_desc as err_val
        FROM latest_data
        WHERE scheme_cat_desc IS NULL OR scheme_cat_desc = ''
        UNION ALL
        SELECT 'launch_date' AS err_col, launch_date as err_val
        FROM latest_data
        WHERE TRY_CAST(launch_date AS DATE) IS NULL AND launch_date <> ''
        """

    @classmethod
    def column_definitions(cls) -> str:
        return """
            TRY_CAST(mf_id AS INTEGER) AS fund_house_id,
            mf_name AS fund_house,
            TRY_CAST(scheme_id AS INTEGER) AS scheme_id,
            scheme_name AS scheme,
            scheme_type_desc AS scheme_type,
            scheme_cat_desc AS scheme_category,
            CASE
                WHEN launch_date <> '' THEN TRY_CAST(launch_date AS DATE)
                ELSE NULL
            END AS launch_date,
            CASE
                WHEN scheme_load = '' THEN NULL
                ELSE scheme_load
            END AS scheme_load,
            CASE
                WHEN scheme_min_amt = '' THEN NULL
                ELSE scheme_min_amt
            END AS scheme_min_amt
        """


class SchemeDocumentView(DedupView):
    """View for scheme document data with deduplication."""

    @classmethod
    def name(cls) -> str:
        return "scheme_document_v"

    @classmethod
    def source_table(cls) -> type[RawTable[Any]]:
        return RawSchemeDocument

    @classmethod
    def id_columns(cls) -> tuple[str, ...]:
        return ("scheme_id",)

    @classmethod
    def pre_check(cls) -> str | None:
        return """
        WITH latest_data AS (
            SELECT scheme_id
            FROM raw_scheme_document
            QUALIFY ROW_NUMBER()
                OVER (PARTITION BY scheme_id ORDER BY loaded_at DESC) = 1
        )
        SELECT 'scheme_id' AS err_col, scheme_id as err_val
        FROM latest_data
        WHERE TRY_CAST(scheme_id AS INTEGER) IS NULL
        """

    @classmethod
    def column_definitions(cls) -> str:
        return """
            TRY_CAST(scheme_id AS INTEGER) AS scheme_id,
            info_document_url,
            summary_pdf_url,
            summary_xls_url,
            summary_xml_url
        """


class SchemeAumView(DedupView):
    """View for scheme AUM data with deduplication."""

    @classmethod
    def name(cls) -> str:
        return "scheme_aum_v"

    @classmethod
    def source_table(cls) -> type[RawTable[Any]]:
        return RawSchemeAum

    @classmethod
    def id_columns(cls) -> tuple[str, ...]:
        return ("plan",)

    @classmethod
    def pre_check(cls) -> str | None:
        return """
        WITH latest_data AS (
            SELECT str_mf_id, str_sd_id,
                scheme_nav_name, average_aum_for_the_quarter, as_at_the_end_of
            FROM raw_scheme_aum
            QUALIFY ROW_NUMBER()
                OVER (PARTITION BY str_sd_id ORDER BY loaded_at DESC) = 1
        )
        SELECT 'mf_id' AS err_col, str_mf_id as err_val
        FROM latest_data
        WHERE TRY_CAST(str_mf_id AS INTEGER) IS NULL
        UNION ALL
        SELECT 'str_sd_id' AS err_col, str_sd_id as err_val
        FROM latest_data
        WHERE TRY_CAST(str_sd_id AS INTEGER) IS NULL
        UNION ALL
        SELECT 'scheme_nav_name' AS err_col, scheme_nav_name as err_val
        FROM latest_data
        WHERE scheme_nav_name IS NULL OR scheme_nav_name = ''
        UNION ALL
        SELECT 'average_aum_for_the_quarter' AS err_col,
            average_aum_for_the_quarter as err_val
        FROM latest_data
        WHERE TRY_CAST(average_aum_for_the_quarter AS DOUBLE) IS NULL
        UNION ALL
        SELECT 'as_at_the_end_of' AS err_col, as_at_the_end_of as err_val
        FROM latest_data
        WHERE TRY_STRPTIME(as_at_the_end_of, '%B-%Y') IS NULL
        """

    @classmethod
    def column_definitions(cls) -> str:
        return """
        TRY_CAST(str_mf_id AS INTEGER) AS fund_house_id,
        TRY_CAST(str_sd_id AS INTEGER) AS scheme_id,
        scheme_nav_name AS plan,
        TRY_CAST(average_aum_for_the_quarter AS DOUBLE) AS aum,
        STRPTIME(as_at_the_end_of, '%B-%Y')::date AS aum_date
        """


class NavPlanDetailsView(DedupView):
    """View for NAV plan details data with deduplication."""

    @classmethod
    def name(cls) -> str:
        return "nav_plan_details_v"

    @classmethod
    def source_table(cls) -> type[RawTable[Any]]:
        return RawNavPlanDetails

    @classmethod
    def id_columns(cls) -> tuple[str, ...]:
        return ("sd_id",)

    @classmethod
    def pre_check(cls) -> str | None:
        return """
        WITH latest_data AS (
            SELECT sd_id, fund_house, scheme, plan
            FROM raw_nav_plan_details
            QUALIFY ROW_NUMBER()
                OVER (PARTITION BY sd_id ORDER BY loaded_at DESC) = 1
        )
        SELECT 'sd_id' AS err_col, sd_id as err_val
        FROM latest_data
        WHERE TRY_CAST(sd_id AS INTEGER) IS NULL
        UNION ALL
        SELECT 'fund_house' AS err_col, fund_house as err_val
        FROM latest_data
        WHERE fund_house IS NULL OR fund_house = ''
        UNION ALL
        SELECT 'scheme' AS err_col, scheme as err_val
        FROM latest_data
        WHERE scheme IS NULL OR scheme = ''
        UNION ALL
        SELECT 'plan' AS err_col, plan as err_val
        FROM latest_data
        WHERE plan IS NULL OR plan = ''
        """

    @classmethod
    def column_definitions(cls) -> str:
        return """
        TRY_CAST(sd_id AS INTEGER) AS sd_id,
        fund_house,
        scheme,
        plan
        """


class NavDedupView(DedupView):
    """View for NAV data with deduplication."""

    @classmethod
    def name(cls) -> str:
        return "nav_v"

    @classmethod
    def source_table(cls) -> type[RawTable[Any]]:
        return RawNav

    @classmethod
    def id_columns(cls) -> tuple[str, ...]:
        return ("sd_id", "hnav_date")

    @classmethod
    def pre_check(cls) -> str | None:
        return """
        WITH latest_data AS (
            SELECT sd_id, nav_name, hnav_amt,
                hnav_date, hnav_dtstamp, hnav_upload_display,
                hnav_reissue, hnav_repurchase
            FROM raw_nav
            QUALIFY ROW_NUMBER()
                OVER (PARTITION BY sd_id ORDER BY loaded_at DESC) = 1
        )
        SELECT 'sd_id' AS err_col, sd_id as err_val
        FROM latest_data
        WHERE TRY_CAST(sd_id AS INTEGER) IS NULL
        UNION ALL
        SELECT 'nav_name' AS err_col, nav_name as err_val
        FROM latest_data
        WHERE nav_name IS NULL OR nav_name = ''
        UNION ALL
        SELECT 'hnav_amt' AS err_col, hnav_amt as err_val
        FROM latest_data
        WHERE TRY_CAST(hnav_amt AS DOUBLE) IS NULL AND hnav_amt <> 'N.A.'
        UNION ALL
        SELECT 'hnav_date' AS err_col, hnav_date as err_val
        FROM latest_data
        WHERE TRY_CAST(hnav_date AS DATE) IS NULL
        UNION ALL
        SELECT 'hnav_dtstamp' AS err_col, hnav_dtstamp as err_val
        FROM latest_data
        WHERE TRY_CAST(hnav_dtstamp AS TIMESTAMP) IS NULL
        UNION ALL
        SELECT 'hnav_upload_display' AS err_col, hnav_upload_display as err_val
        FROM latest_data
        WHERE TRY_STRPTIME(hnav_upload_display, '%d %b %Y %H:%M:%S') IS NULL
        UNION ALL
        SELECT 'hnav_reissue' AS err_col, hnav_reissue as err_val
        FROM latest_data
        WHERE TRY_CAST(hnav_reissue AS DOUBLE) IS NULL
            AND hnav_reissue NOT IN ('', 'N.A.')
        UNION ALL
        SELECT 'hnav_repurchase' AS err_col, hnav_repurchase as err_val
        FROM latest_data
        WHERE TRY_CAST(hnav_repurchase AS DOUBLE) IS NULL
            AND hnav_repurchase NOT IN ('', 'N.A.')
        """

    @classmethod
    def column_definitions(cls) -> str:
        return """
        TRY_CAST(sd_id AS INTEGER) AS sd_id,
        nav_name AS plan,
        CASE 
            WHEN hnav_amt = 'N.A.' THEN NULL 
            ELSE TRY_CAST(hnav_amt AS DOUBLE) 
        END AS nav,
        TRY_CAST(hnav_date AS DATE) AS date,
        TRY_CAST(hnav_dtstamp AS TIMESTAMP) AS nav_ts,
        STRPTIME(hnav_upload_display, '%d %b %Y %H:%M:%S') AS nav_upload_ts,
        CASE
            WHEN hnav_reissue IN ('', 'N.A.') THEN NULL
            ELSE TRY_CAST(hnav_reissue AS DOUBLE)
        END AS nav_reissue,
        CASE
            WHEN hnav_repurchase IN ('', 'N.A.') THEN NULL
            ELSE TRY_CAST(hnav_repurchase AS DOUBLE)
        END AS nav_repurchase,
        CASE WHEN isin_ri = '' THEN NULL ELSE isin_ri END AS isin_reissue,
        CASE WHEN isin_po = '' THEN NULL ELSE isin_po END AS isin_repurchase
        """


NavView = NavDedupView


DEDUP_VIEWS = (
    FundHouseView,
    SchemeView,
    SchemeDocumentView,
    SchemeAumView,
    NavPlanDetailsView,
    NavDedupView,
)
