"""Enums for AMC portfolio scrapers."""

import sys
from enum import Enum

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    class StrEnum(str, Enum):
        """Fallback StrEnum for Python < 3.11."""

        def __str__(self) -> str:
            return str(self.value)


class DisclosureFrequency(StrEnum):
    """Frequency of portfolio disclosure."""

    MONTHLY = "monthly"
    FORTNIGHTLY = "fortnightly"
    HALF_YEARLY = "half_yearly"


class BroadAssetCategory(StrEnum):
    """Broad asset category classification."""

    EQUITY = "Equity"
    DEBT = "Debt"
    CASH = "Cash"
    COMMODITY = "Commodity"
    DERIVATIVE = "Derivative"
    OTHER = "Other"


class ScraperFundHouse(Enum):
    """AMFI Fund House ID mapping for scrapers."""

    ABSL = 3
    HDFC = 9
