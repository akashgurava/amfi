"""Portfolio statements and holdings domain package."""

from .base import BasePortfolioScraper, normalize_scheme_name
from .enums import BroadAssetCategory, DisclosureFrequency, ScraperFundHouse
from .models import (
    DisclosureMeta,
    HoldingCandidate,
    RejectedRowRecord,
    StatementMeta,
    ValidatedHolding,
)
from .repo import HoldingsRepository
from .tables import (
    HOLDINGS_TABLES,
    RawAmcMasterAbsl,
    RawHoldingSections,
    RawInstrumentMaster,
    RawPortfolioStatement,
    RawRejectedAmcHoldings,
    RawSchemeHoldings,
)
from .validator import RowValidator, categorize_section
from .views import (
    HOLDINGS_VIEWS,
    PortfolioStatementView,
    SchemeHoldingsView,
)
from .amc.absl import AbslPortfolioScraper

__all__ = [
    # Scrapers
    "BasePortfolioScraper",
    "AbslPortfolioScraper",
    "normalize_scheme_name",
    # Enums
    "DisclosureFrequency",
    "BroadAssetCategory",
    "ScraperFundHouse",
    # Models
    "DisclosureMeta",
    "StatementMeta",
    "HoldingCandidate",
    "ValidatedHolding",
    "RejectedRowRecord",
    # Validation & Repo
    "RowValidator",
    "categorize_section",
    "HoldingsRepository",
    # Tables
    "HOLDINGS_TABLES",
    "RawAmcMasterAbsl",
    "RawHoldingSections",
    "RawInstrumentMaster",
    "RawPortfolioStatement",
    "RawSchemeHoldings",
    "RawRejectedAmcHoldings",
    # Views
    "HOLDINGS_VIEWS",
    "SchemeHoldingsView",
    "PortfolioStatementView",
]
