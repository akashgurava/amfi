"""Response models for AMFI official portal API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _as_str(value: Any) -> str:
    """Coerce ``value`` to a string, mapping ``None`` to the empty string."""
    return "" if value is None else str(value)


@dataclass(frozen=True)
class RawFundHouseResponse:
    """Raw response from AMFI API for fund houses."""

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
            amc_schemewise_annual_report=_as_str(data.get("amc_schemewise_annual_report")),
            amc_fortnightly_portfolio_disclosure=_as_str(data.get("amc_fortnightly_portfolio_disclosure")),
            amc_monthly_portfolio_disclosure=_as_str(data.get("amc_monthly_portfolio_disclosure")),
            amc_halfYearly_portfolio_disclosure=_as_str(data.get("amc_halfYearly_portfolio_disclosure")),
            amc_monthly_mf_factsheets=_as_str(data.get("amc_monthly_mf_factsheets")),
            amc_riskometer_monthly=_as_str(data.get("amc_riskometer_monthly")),
            amc_riskometer_yearly=_as_str(data.get("amc_riskometer_yearly")),
            amc_unclaimed_dividend_amt=_as_str(data.get("amc_unclaimed_dividend_amt")),
            amc_unclaimed_redemption_amt=_as_str(data.get("amc_unclaimed_redemption_amt")),
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
            average_aum_for_the_quarter=_as_str(data.get("Average_AUM_For_The_Quarter")),
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
