"""Compatibility shim re-exporting dedup views from amfi.derived."""

from ..derived import (
    DEDUP_VIEWS,
    DedupView,
    FundHouseView,
    NavPlanDetailsView,
    NavView,
    SchemeAumView,
    SchemeDocumentView,
    SchemeView,
)

__all__ = [
    "DEDUP_VIEWS",
    "DedupView",
    "FundHouseView",
    "NavPlanDetailsView",
    "NavView",
    "SchemeAumView",
    "SchemeDocumentView",
    "SchemeView",
]
