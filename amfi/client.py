"""Compatibility shim re-exporting AmfiClient from amfi.portal."""

from .portal.client import (
    AmfiClient,
    DateLike,
    MultiWindowRateLimiter,
    RateLimitRule,
    ResponsePayloadError,
    SchemeListItem,
    _date_key,
    _to_date,
)

__all__ = [
    "AmfiClient",
    "DateLike",
    "MultiWindowRateLimiter",
    "RateLimitRule",
    "ResponsePayloadError",
    "SchemeListItem",
    "_date_key",
    "_to_date",
]
