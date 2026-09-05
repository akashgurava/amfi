"""Validation engine for AMC portfolio holdings."""

import json
import logging
import math
import re
from typing import Any

from .enums import BroadAssetCategory
from .models import HoldingCandidate, RejectedRowRecord, ValidatedHolding

logger = logging.getLogger(__name__)

# Standard 12-character ISIN regex (e.g. INE090A01021, IN0020240134)
ISIN_REGEX = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def categorize_section(section_name: str) -> BroadAssetCategory:
    """Classify AMC section name into broad asset category."""
    sec = section_name.upper()
    if any(k in sec for k in ["EQUITY", "SHARE", "STOCK"]):
        return BroadAssetCategory.EQUITY
    if any(
        k in sec
        for k in [
            "DEBT",
            "BOND",
            "GILT",
            "DEBENTURE",
            "COMMERCIAL PAPER",
            "CERTIFICATE OF DEPOSIT",
            "TREASURY",
            "SOVEREIGN",
            "GOVERNMENT",
            "G-SEC",
            "GSEC",
            "FIXED INCOME",
            "NCD",
        ]
    ):
        return BroadAssetCategory.DEBT
    if any(
        k in sec
        for k in [
            "TREPS",
            "REPO",
            "CASH",
            "BANK",
            "CURRENT ASSET",
            "RECEIVABLE",
            "PAYABLE",
            "MARGIN",
            "COLLATERAL",
        ]
    ):
        return BroadAssetCategory.CASH
    if any(k in sec for k in ["SILVER", "GOLD", "COMMODITY"]):
        return BroadAssetCategory.COMMODITY
    if any(k in sec for k in ["DERIVATIVE", "FUTURES", "OPTIONS", "SWAP", "IRS"]):
        return BroadAssetCategory.DERIVATIVE
    return BroadAssetCategory.OTHER


class RowValidator:
    """Validator enforcing the golden data validation rules on holding rows."""

    def __init__(self, amc_name: str, scheme_name: str):
        self.amc_name = amc_name
        self.scheme_name = scheme_name

    def parse_market_value(self, val: Any) -> float | None:
        """Parse market value into float. Returns None if invalid/missing."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            if math.isnan(val) or math.isinf(val):
                return None
            return float(val)
        s = str(val).strip().replace(",", "")
        if not s or s in ("-", "N.A.", "NA", "NIL", "NULL", "NONE"):
            return None
        try:
            res = float(s)
            return None if (math.isnan(res) or math.isinf(res)) else res
        except (ValueError, TypeError):
            return None

    def parse_aum_pct(self, val: Any) -> float | None:
        """
        Parse AUM % into float on a 0-100 scale (e.g. 6.0501 for 6.0501%).
        Cleans '$0.00%', '<0.01%', '0.05%', etc.
        """
        if val is None:
            return None
        if isinstance(val, (int, float)):
            if math.isnan(val) or math.isinf(val):
                return None
            # If Excel stored decimal fraction (e.g. 0.0605 for 6.05%), scale to percentage
            # Note: in rare cases where single holding is > 100% (leveraged), keep in mind
            return round(float(val) * 100.0, 4)

        s = (
            str(val)
            .strip()
            .replace("$", "")
            .replace("%", "")
            .replace("<", "")
            .replace(",", "")
            .strip()
        )
        if not s or s in ("-", "N.A.", "NA", "NIL", "NULL", "NONE"):
            return None
        try:
            res = float(s)
            if math.isnan(res) or math.isinf(res):
                return None
            return round(res, 4)
        except (ValueError, TypeError):
            return None

    def parse_optional_float(self, val: Any) -> float | None:
        """Parse optional numeric field (quantity, ytm, ytc)."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            if math.isnan(val) or math.isinf(val):
                return None
            return float(val)
        s = str(val).strip().replace(",", "").replace("%", "").strip()
        if not s or s in ("-", "N.A.", "NA", "NIL", "NULL", "NONE"):
            return None
        try:
            res = float(s)
            return None if (math.isnan(res) or math.isinf(res)) else res
        except (ValueError, TypeError):
            return None

    def validate_isin(self, isin_raw: Any) -> tuple[str | None, str | None]:
        """
        Validate ISIN.
        Returns (cleaned_isin, error_reason).
        If cash/none, returns (None, None).
        """
        if isin_raw is None:
            return None, None
        s = str(isin_raw).strip().upper()
        if not s or s in ("-", "N.A.", "NA", "NIL", "NULL", "NONE", "UNLISTED"):
            return None, None
        if ISIN_REGEX.match(s):
            return s, None
        return None, f"Invalid ISIN format '{s}' (expected 12 alphanumeric characters)"

    def validate(
        self, candidate: HoldingCandidate
    ) -> tuple[ValidatedHolding | None, RejectedRowRecord | None]:
        """
        Validate a Candidate holding row.
        Returns (ValidatedHolding, None) on success.
        Returns (None, RejectedRowRecord) on failure and logs DEBUG.
        """
        raw_row_str = json.dumps(candidate.raw_row, default=str)

        # Rule 1: Instrument Name must not be empty
        inst_name = (
            str(candidate.instrument_name).strip()
            if candidate.instrument_name is not None
            else ""
        )
        if not inst_name or inst_name in ("-", "N.A.", "NA", "NIL"):
            reason = "Instrument name is missing or empty"
            logger.debug(
                "Rejected row %d in %s [%s]: %s. Raw: %s",
                candidate.line_number,
                candidate.sheet_name,
                self.scheme_name,
                reason,
                raw_row_str,
            )
            return None, RejectedRowRecord(
                amc=self.amc_name,
                scheme=self.scheme_name,
                sheet_name=candidate.sheet_name,
                line_number=candidate.line_number,
                raw_row=raw_row_str,
                reason=reason,
                full_reason=f"Instrument name resolved to '{inst_name}'",
            )

        # Rule 2: Market value must be valid non-null float
        mv = self.parse_market_value(candidate.market_value_lakhs)
        if mv is None:
            reason = "Invalid or missing market_value_lakhs"
            logger.debug(
                "Rejected row %d in %s [%s]: %s (raw: %r). Raw: %s",
                candidate.line_number,
                candidate.sheet_name,
                self.scheme_name,
                reason,
                candidate.market_value_lakhs,
                raw_row_str,
            )
            return None, RejectedRowRecord(
                amc=self.amc_name,
                scheme=self.scheme_name,
                sheet_name=candidate.sheet_name,
                line_number=candidate.line_number,
                raw_row=raw_row_str,
                reason=reason,
                full_reason=f"market_value_lakhs raw value was {candidate.market_value_lakhs!r}",
            )

        # Rule 3: AUM % must be valid non-null float
        aum_pct = self.parse_aum_pct(candidate.aum_pct)
        if aum_pct is None:
            reason = "Invalid or missing aum_pct"
            logger.debug(
                "Rejected row %d in %s [%s]: %s (raw: %r). Raw: %s",
                candidate.line_number,
                candidate.sheet_name,
                self.scheme_name,
                reason,
                candidate.aum_pct,
                raw_row_str,
            )
            return None, RejectedRowRecord(
                amc=self.amc_name,
                scheme=self.scheme_name,
                sheet_name=candidate.sheet_name,
                line_number=candidate.line_number,
                raw_row=raw_row_str,
                reason=reason,
                full_reason=f"aum_pct raw value was {candidate.aum_pct!r}",
            )

        # Rule 4: ISIN validation
        isin, isin_err = self.validate_isin(candidate.isin)
        if isin_err:
            logger.debug(
                "Rejected row %d in %s [%s]: %s. Raw: %s",
                candidate.line_number,
                candidate.sheet_name,
                self.scheme_name,
                isin_err,
                raw_row_str,
            )
            return None, RejectedRowRecord(
                amc=self.amc_name,
                scheme=self.scheme_name,
                sheet_name=candidate.sheet_name,
                line_number=candidate.line_number,
                raw_row=raw_row_str,
                reason="Invalid ISIN format",
                full_reason=isin_err,
            )

        # Parse optional fields
        quantity = self.parse_optional_float(candidate.quantity)
        ytm_pct = self.parse_optional_float(candidate.ytm_pct)
        ytc_pct = self.parse_optional_float(candidate.ytc_pct)

        # If YTM was given as fraction (e.g. 0.0748), scale to percent
        if ytm_pct is not None and 0 < ytm_pct < 1.0:
            ytm_pct = round(ytm_pct * 100.0, 4)
        if ytc_pct is not None and 0 < ytc_pct < 1.0:
            ytc_pct = round(ytc_pct * 100.0, 4)

        industry_or_rating = (
            str(candidate.industry_or_rating).strip()
            if candidate.industry_or_rating is not None
            else None
        )
        if industry_or_rating in ("-", "N.A.", "NA", "NIL", ""):
            industry_or_rating = None

        broad_cat = categorize_section(candidate.section_name)

        validated = ValidatedHolding(
            sheet_name=candidate.sheet_name,
            line_number=candidate.line_number,
            section_name=candidate.section_name,
            broad_category=broad_cat,
            instrument_name=inst_name,
            isin=isin,
            industry_or_rating=industry_or_rating,
            quantity=quantity,
            market_value_lakhs=mv,
            aum_pct=aum_pct,
            ytm_pct=ytm_pct,
            ytc_pct=ytc_pct,
        )
        return validated, None
