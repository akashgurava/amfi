from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import RawTable


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


class RawFundHouse(RawTable[RawFundHouseResponse]):
    """Raw table for fund house data.
    Mainly used for fund_house_id, fund_house, and amc_name.
    """

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
    """Raw table for scheme data.

    Mainly used for scheme_id, scheme_name, and launch_date.
    """

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
    """Raw table for scheme document data.

    Contains document URLs for each scheme. No column of importance/analysis.
    """

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
    """Raw table for scheme AUM data.

    Mainly used for scheme_id and aum.
    """

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
    """Raw table for NAV plan details data.

    Mainly used for sd_id, fund_house, scheme, and plan.
    """

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
    """Raw table for NAV data.

    Mainly used for sd_id and hnav_amt.
    """

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


RAW_TABLES: tuple[type[RawTable[Any]], ...] = (
    RawFundHouse,
    RawScheme,
    RawSchemeDocument,
    RawSchemeAum,
    RawNav,
    RawNavPlanDetails,
)
