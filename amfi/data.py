from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from .error import AppConfigError

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


def _as_str(value: Any) -> str:
    """Coerce ``value`` to a string, mapping ``None`` to the empty string."""
    return "" if value is None else str(value)


@dataclass(frozen=True)
class RawFundHouseResponse:
    """
    Raw response from AMFI API for fund houses.
    """

    mf_id: str
    mf_name: str
    amc_name: str
    amc_website: str
    amc_schemewise_annual_report: str
    amc_fortnightly_portfolio_disclosure: str
    amc_monthly_portfolio_disclosure: str
    amc_halfYearly_portfolio_disclosure: str
    amc_monthly_mf_factsheets: str
    amc_riskometer_monthly: str
    amc_riskometer_yearly: str
    amc_unclaimed_dividend_amt: str
    amc_unclaimed_redemption_amt: str
    amc_investonline_in_mf: str
    rss_latest_nav: str
    rss_latest_aum: str
    statement_of_information: str
    scheme_wise: str
    icon_wordmark: str
    icons: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawFundHouseResponse:
        return cls(
            mf_id=_as_str(data.get("mf_id")),
            mf_name=_as_str(data.get("mf_name")),
            amc_name=_as_str(data.get("amc_name")),
            amc_website=_as_str(data.get("amc_website")),
            amc_schemewise_annual_report=_as_str(
                data.get("amc_schemewise_annual_report")
            ),
            amc_fortnightly_portfolio_disclosure=_as_str(
                data.get("amc_fortnightly_portfolio_disclosure")
            ),
            amc_monthly_portfolio_disclosure=_as_str(
                data.get("amc_monthly_portfolio_disclosure")
            ),
            amc_halfYearly_portfolio_disclosure=_as_str(
                data.get("amc_halfYearly_portfolio_disclosure")
            ),
            amc_monthly_mf_factsheets=_as_str(data.get("amc_monthly_mf_factsheets")),
            amc_riskometer_monthly=_as_str(data.get("amc_riskometer_monthly")),
            amc_riskometer_yearly=_as_str(data.get("amc_riskometer_yearly")),
            amc_unclaimed_dividend_amt=_as_str(data.get("amc_unclaimed_dividend_amt")),
            amc_unclaimed_redemption_amt=_as_str(
                data.get("amc_unclaimed_redemption_amt")
            ),
            amc_investonline_in_mf=_as_str(data.get("amc_investonline_in_mf")),
            rss_latest_nav=_as_str(data.get("rss_latest_nav")),
            rss_latest_aum=_as_str(data.get("rss_latest_aum")),
            statement_of_information=_as_str(data.get("statement_of_information")),
            scheme_wise=_as_str(data.get("scheme_wise")),
            icon_wordmark=_as_str(data.get("icon_wordmark")),
            icons=_as_str(data.get("icons")),
        )

    def __str__(self) -> str:
        return f"FundHouse(mf_id={self.mf_id}, mf_name={self.mf_name})"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.mf_id:
            raise ValueError("mf_id is required")
        if not self.mf_id.isdigit():
            raise ValueError(f"mf_id must be a digit, got: {self.mf_id}")
        if not self.mf_name:
            raise ValueError("mf_name is required")
        if not self.amc_name:
            raise ValueError("amc_name is required")


@dataclass(frozen=True)
class RawSchemeResponse:
    """Raw response from AMFI ``scheme-details`` API for one scheme."""

    mf_id: str
    mf_name: str
    scheme_id: str
    scheme_name: str
    scheme_objective: str
    scheme_type_desc: str
    scheme_cat_desc: str
    launch_date: str
    scheme_load: str
    scheme_min_amt: str
    amc_website: str

    def __post_init__(self) -> None:
        if not self.scheme_id:
            raise ValueError("scheme_id is required")
        if not self.mf_id:
            raise ValueError("mf_id is required")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawSchemeResponse:
        return cls(
            mf_id=_as_str(data.get("MF_Id")),
            mf_name=_as_str(data.get("MF_Name")),
            scheme_id=_as_str(data.get("scheme_Id")),
            scheme_name=_as_str(data.get("Scheme_Name")),
            scheme_objective=_as_str(data.get("Scheme_Objective")),
            scheme_type_desc=_as_str(data.get("SchemeType_Desc")),
            scheme_cat_desc=_as_str(data.get("SchemeCat_Desc")),
            launch_date=_as_str(data.get("Launch_Date")),
            scheme_load=_as_str(data.get("Scheme_load")),
            scheme_min_amt=_as_str(data.get("Scheme_min_amt")),
            amc_website=_as_str(data.get("AMC_Website")),
        )


@dataclass(frozen=True)
class RawSchemeDocumentResponse:
    """Raw response from AMFI ``schemes/{id}/documents`` API."""

    scheme_id: str
    info_document_url: str
    summary_pdf_url: str
    summary_xls_url: str
    summary_xml_url: str

    def __post_init__(self) -> None:
        if not self.scheme_id:
            raise ValueError("scheme_id is required")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawSchemeDocumentResponse:
        return cls(
            scheme_id=_as_str(data.get("schemeId")),
            info_document_url=_as_str(data.get("infoDocumentUrl")),
            summary_pdf_url=_as_str(data.get("summaryPdfUrl")),
            summary_xls_url=_as_str(data.get("summaryXlsUrl")),
            summary_xml_url=_as_str(data.get("summaryXmlUrl")),
        )


@dataclass(frozen=True)
class RawSchemeAumResponse:
    """Raw response from AMFI ``scheme-data?strOption=AUM`` API."""

    str_mf_id: str
    str_sd_id: str
    scheme_nav_name: str
    average_aum_for_the_quarter: str
    as_at_the_end_of: str
    str_option: str

    def __post_init__(self) -> None:
        if not self.str_sd_id:
            raise ValueError("str_sd_id is required")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawSchemeAumResponse:
        return cls(
            scheme_nav_name=_as_str(data.get("Scheme_NAV_Name")),
            average_aum_for_the_quarter=_as_str(
                data.get("Average_AUM_For_The_Quarter")
            ),
            as_at_the_end_of=_as_str(data.get("As_At_The_End_Of")),
            str_mf_id=_as_str(data.get("strMFId")),
            str_option=_as_str(data.get("strOption")),
            str_sd_id=_as_str(data.get("strSDId")),
        )


@dataclass(frozen=True)
class RawNavPlanDetailsResponse:
    """Fund house/scheme/plan metadata derived from a NAV payload."""

    sd_id: str
    fund_house: str
    scheme: str
    plan: str


@dataclass(frozen=True)
class RawNavResponse:
    """Single NAV row from the AMFI ``nav-history`` API."""

    sd_id: str
    nav_name: str
    hnav_amt: str
    isin_ri: str
    isin_po: str
    hnav_date: str
    hnav_dtstamp: str
    hnav_reissue: str
    hnav_repurchase: str
    hnav_upload_display: str

    def __post_init__(self) -> None:
        if not self.sd_id:
            raise ValueError("sd_id is required")
        if not self.nav_name:
            raise ValueError("nav_name is required")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawNavResponse:
        return cls(
            sd_id=_as_str(data.get("SD_ID")),
            nav_name=_as_str(data.get("NAV_Name")),
            hnav_amt=_as_str(data.get("hNAV_Amt")),
            isin_ri=_as_str(data.get("ISIN_RI")),
            isin_po=_as_str(data.get("ISIN_PO")),
            hnav_date=_as_str(data.get("hNAV_Date")),
            hnav_dtstamp=_as_str(data.get("hNAV_Dtstamp")),
            hnav_reissue=_as_str(data.get("hNAV_reissue")),
            hnav_repurchase=_as_str(data.get("hNAV_repurchase")),
            hnav_upload_display=_as_str(data.get("hNAV_Upload_display")),
        )


class Table(Protocol):
    """
    Protocol for database tables.
    """

    @classmethod
    def name(cls) -> str:
        """Name of the table."""
        ...

    @classmethod
    def create(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        """Create SQL for the table."""
        ...


class RawTable(Table, Protocol[T_co]):
    """
    Protocol for raw database tables.
    """

    @classmethod
    def row_type(cls) -> type[T_co]:
        """Row type of the table."""
        ...

    @classmethod
    def id_columns(cls) -> tuple[str, ...]:
        """
        Columns that uniquely identify a row in the table.
        For raw tables this is usually just a combination of cid columns.
        """
        ...

    @classmethod
    def create(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        """
        Create SQL for the raw table.

        Args:
            if_not_exists: If True, the table will be created if it doesn't exist.
            replace: If True, the table will be replaced if it exists.

        Returns:
            Create SQL for the table.
        """
        if if_not_exists and replace:
            raise AppConfigError(
                "if_not_exists and replace",
                "BOTH_CANNOT_BE_TRUE",
                (if_not_exists, replace),
            )

        if replace:
            prefix = "OR REPLACE TABLE"
        else:
            prefix = "TABLE IF NOT EXISTS"

        return f"""
            CREATE {prefix} {cls.name()} (
                {cls.column_definitions()}
                loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """

    @classmethod
    def column_definitions(cls) -> str:
        """
        Column definitions for the table used while creating the table.
        Usually looks like
        ```sql
        id TEXT NOT NULL PRIMARY KEY,
        name TEXT NOT NULL
        ```
        """
        ...

    @classmethod
    def insert_columns(cls) -> tuple[str, ...]:
        """
        Columns orderd as per their insert order.
        Usually looks like
        ```python
        ("id", "name")
        ```
        """
        ...

    @classmethod
    def insert_sql(cls) -> str:
        columns = cls.insert_columns()
        placeholders = ", ".join(["?"] * len(columns))
        columns_sql = ", ".join(columns)
        return f"INSERT INTO {cls.name()} ({columns_sql}) VALUES ({placeholders})"

    @classmethod
    def existing_id_sql(cls) -> str:
        id_columns = cls.id_columns()
        return f"SELECT DISTINCT {', '.join(id_columns)} FROM {cls.name()}"


class RawFundHouse(RawTable[RawFundHouseResponse]):
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


class View(Table, Protocol):
    @classmethod
    def source_table(cls) -> type[Table]:
        """
        Source table for the view.
        """
        ...

    @classmethod
    def id_columns(cls) -> tuple[str, ...]:
        """
        Columns to use as partition keys in the view.
        """
        ...

    @classmethod
    def pre_check(cls) -> str | None:
        """
        Pre check sql to validate if data is valid.
        Returns None if no check is needed.
        """
        ...

    @classmethod
    def column_definitions(cls) -> str:
        """
        Column definitions for the view used while creating the view.
        Usually looks like
        ```sql
        mf_id::int AS mf_id,
        mf_name
        ```
        """
        ...

    @classmethod
    def create(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        """
        SQL to create the view.
        Returns None if no creation is needed.
        """
        if if_not_exists and replace:
            raise AppConfigError(
                "if_not_exists and replace",
                "BOTH_CANNOT_BE_TRUE",
                (if_not_exists, replace),
            )

        if replace:
            prefix = "OR REPLACE VIEW"
        else:
            prefix = "VIEW IF NOT EXISTS"

        return f"""
        CREATE {prefix} {cls.name()} AS
        SELECT {cls.column_definitions()} FROM {cls.source_table().name()}
        QUALIFY ROW_NUMBER()
            OVER (PARTITION BY {",".join(cls.id_columns())} ORDER BY loaded_at DESC) = 1
        """


class FundHouseView(View):
    @classmethod
    def name(cls) -> str:
        return "fund_house_v"

    @classmethod
    def source_table(cls) -> type[Table]:
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


class SchemeView(View):
    @classmethod
    def name(cls) -> str:
        return "scheme_v"

    @classmethod
    def source_table(cls) -> type[Table]:
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


class SchemeDocumentView(View):
    @classmethod
    def name(cls) -> str:
        return "scheme_document_v"

    @classmethod
    def source_table(cls) -> type[Table]:
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


class SchemeAumView(View):
    @classmethod
    def name(cls) -> str:
        return "scheme_aum_v"

    @classmethod
    def source_table(cls) -> type[Table]:
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


class NavPlanDetailsView(View):
    @classmethod
    def name(cls) -> str:
        return "nav_plan_details_v"

    @classmethod
    def source_table(cls) -> type[Table]:
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


class NavView(View):
    @classmethod
    def name(cls) -> str:
        return "nav_v"

    @classmethod
    def source_table(cls) -> type[Table]:
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


class PlansActiveView(View):
    """Active plans view."""

    @classmethod
    def name(cls) -> str:
        return "plans_active_v"


RAW_TABLES: tuple[type[RawTable[Any]], ...] = (
    RawFundHouse,
    RawScheme,
    RawSchemeDocument,
    RawSchemeAum,
    RawNav,
    RawNavPlanDetails,
)


VIEWS: tuple[type[View], ...] = (
    FundHouseView,
    SchemeView,
    SchemeDocumentView,
    SchemeAumView,
    NavPlanDetailsView,
    NavView,
)
