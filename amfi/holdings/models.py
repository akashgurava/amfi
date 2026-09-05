"""Data models for AMC portfolio scrapers."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .enums import BroadAssetCategory, DisclosureFrequency


@dataclass(slots=True)
class DisclosureMeta:
    """Metadata for an AMC portfolio disclosure publication."""

    fund_house_id: int
    as_on_date: date
    title: str
    download_url: str
    frequency: DisclosureFrequency = DisclosureFrequency.MONTHLY


@dataclass(slots=True)
class HoldingCandidate:
    """Raw unvalidated holding row parsed from a statement sheet."""

    sheet_name: str
    line_number: int
    raw_row: list[Any]
    section_name: str
    instrument_name: Any
    isin: Any
    industry_or_rating: Any
    quantity: Any
    market_value_lakhs: Any
    aum_pct: Any
    ytm_pct: Any = None
    ytc_pct: Any = None


@dataclass(slots=True)
class ValidatedHolding:
    """Holding row that passed all data validation checks."""

    sheet_name: str
    line_number: int
    section_name: str
    broad_category: BroadAssetCategory
    instrument_name: str
    isin: str | None
    industry_or_rating: str | None
    quantity: float | None
    market_value_lakhs: float
    aum_pct: float
    ytm_pct: float | None = None
    ytc_pct: float | None = None


@dataclass(slots=True)
class RejectedRowRecord:
    """Record of a row failing validation, stored in raw_rejected_amc_holdings."""

    amc: str
    scheme: str
    sheet_name: str
    line_number: int
    raw_row: str
    reason: str
    full_reason: str = ""


@dataclass(slots=True)
class StatementMeta:
    """Header metadata for a scheme's portfolio statement."""

    fund_house_id: int
    scheme_id: int
    amc_sheet_name: str
    amc_scheme_name: str
    portfolio_date: date
    frequency: DisclosureFrequency = DisclosureFrequency.MONTHLY
    statement_id: int | None = None
    total_aum_lakhs: float | None = None
    source_file: str = ""
    holding_count: int = 0
    rejected_count: int = 0
    holdings: list[ValidatedHolding] = field(default_factory=list)
    rejections: list[RejectedRowRecord] = field(default_factory=list)
