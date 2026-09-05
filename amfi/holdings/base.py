"""Abstract base class and utilities for AMC portfolio scrapers."""

import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

import duckdb
import httpx

from .enums import DisclosureFrequency
from .models import DisclosureMeta, StatementMeta
from .repo import HoldingsRepository

logger = logging.getLogger(__name__)


def normalize_scheme_name(s: str) -> str:
    """Standard alphanumeric normalization for mutual fund scheme names."""
    s = s.upper().strip()
    s = re.sub(r"^(ADITYA\s+BIRLA\s+SUN\s+LIFE\s+|ABSL\s+|BIRLA\s+SUN\s+LIFE\s+|HDFC\s+|ICICI\s+PRUDENTIAL\s+|SBI\s+)", "", s)
    s = s.replace("&", "AND")
    s = re.sub(r"\bFUND\s+OF\s+FUND\b", "FOF", s)
    s = re.sub(r"\bBONDS\b", "BOND", s)
    s = re.sub(r"\bAPR\b", "APRIL", s)
    s = re.sub(r"\bJUN\b", "JUNE", s)
    s = re.sub(r"\bJUL\b", "JULY", s)
    s = re.sub(r"\bSEP\b", "SEPTEMBER", s)
    s = re.sub(r"\bOCT\b", "OCTOBER", s)
    s = re.sub(r"\bNOV\b", "NOVEMBER", s)
    s = re.sub(r"\bDEC\b", "DECEMBER", s)
    s = re.sub(r"\bJAN\b", "JANUARY", s)
    s = re.sub(r"\bFEB\b", "FEBRUARY", s)
    s = re.sub(r"\bMAR\b", "MARCH", s)
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s


class BasePortfolioScraper(ABC):
    """Abstract base class for AMC portfolio disclosure scrapers."""

    fund_house_id: int
    amc_name: str

    def __init__(self, db_conn: duckdb.DuckDBPyConnection | None = None):
        self.conn = db_conn
        self.db = HoldingsRepository(db_conn) if db_conn else None

    @abstractmethod
    def list_disclosures(
        self,
        frequency: DisclosureFrequency = DisclosureFrequency.MONTHLY,
    ) -> list[DisclosureMeta]:
        """List available portfolio disclosures published by the AMC."""
        raise NotImplementedError

    def download_disclosure(
        self,
        disclosure: DisclosureMeta,
        cache_dir: Path | None = None,
    ) -> bytes:
        """
        Download disclosure file bytes with optional local disk caching.
        """
        if cache_dir:
            cache_dir = Path(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            # Safe filename
            safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", Path(disclosure.download_url).name)
            if not safe_name.endswith(".zip"):
                safe_name = f"{disclosure.as_on_date}_{safe_name}.zip"
            cache_file = cache_dir / safe_name
            if cache_file.exists() and cache_file.stat().st_size > 0:
                logger.debug("Loading cached disclosure from %s", cache_file)
                return cache_file.read_bytes()

        logger.info("Downloading portfolio disclosure from %s", disclosure.download_url)
        with httpx.Client(verify=False, timeout=60.0, follow_redirects=True) as client:
            resp = client.get(disclosure.download_url)
            resp.raise_for_status()
            data = resp.content

        if cache_dir:
            cache_file.write_bytes(data)
            logger.debug("Saved disclosure to cache at %s", cache_file)

        return data

    @abstractmethod
    def parse_disclosure(
        self,
        raw_bytes: bytes,
        disclosure: DisclosureMeta,
        filter_schemes: list[str] | None = None,
    ) -> list[StatementMeta]:
        """
        Parse downloaded disclosure payload into validated StatementMeta objects.
        """
        raise NotImplementedError

    @abstractmethod
    def resolve_scheme_id(
        self,
        amc_identifier: str,
        amc_scheme_name: str,
    ) -> int | None:
        """
        Resolve AMFI scheme_id using AMC master table, short codes, or normalized name matching.
        """
        raise NotImplementedError

    def ingest_disclosure(
        self,
        disclosure: DisclosureMeta,
        cache_dir: Path | None = None,
        filter_schemes: list[str] | None = None,
        overwrite: bool = True,
    ) -> list[StatementMeta]:
        """
        End-to-end ingestion pipeline:
        1. Downloads disclosure (with cache).
        2. Parses into validated StatementMeta objects.
        3. Persists statements, holdings, rejections, and AMC master mappings into DuckDB.
        """
        if not self.db:
            raise ValueError("Cannot ingest disclosure without a configured DuckDB connection.")

        raw_bytes = self.download_disclosure(disclosure, cache_dir=cache_dir)
        statements = self.parse_disclosure(
            raw_bytes, disclosure, filter_schemes=filter_schemes
        )

        total_holdings = 0
        total_rejections = 0
        for stmt in statements:
            self.db.save_statement(stmt, overwrite=overwrite)
            total_holdings += len(stmt.holdings)
            total_rejections += len(stmt.rejections)

        logger.info(
            "Ingestion complete for %s [%s]: %d statements, %d holdings accepted, %d rejected.",
            self.amc_name,
            disclosure.as_on_date,
            len(statements),
            total_holdings,
            total_rejections,
        )
        return statements
