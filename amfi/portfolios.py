"""Compatibility shim re-exporting portfolio domain from amfi.portfolios."""

from .portfolios.builder import PORTFOLIO_ID_OFFSET, PortfolioBuilder
from .portfolios.config import PortfolioConfig, load_portfolios

__all__ = [
    "PORTFOLIO_ID_OFFSET",
    "PortfolioBuilder",
    "PortfolioConfig",
    "load_portfolios",
]
