"""Database helper for persisting and querying portfolio disclosures and holdings."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import duckdb

from .models import StatementMeta

logger = logging.getLogger(__name__)


class HoldingsRepository:
    """Helper for persisting statements, validated holdings, and rejections into DuckDB."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn
        self._section_cache: dict[str, int] = {}
        self._instrument_cache: dict[tuple[str, str | None, str | None], int] = {}

    def get_or_create_section_id(self, section_name: str, broad_category: str) -> int:
        """Get or create section_id for the raw section name."""
        sec_clean = section_name.strip()
        if sec_clean in self._section_cache:
            return self._section_cache[sec_clean]

        res = self.conn.execute(
            "SELECT section_id FROM raw_holding_sections WHERE section_name = ?",
            [sec_clean],
        ).fetchone()

        if res:
            sec_id = int(res[0])
        else:
            sec_id = int(
                self.conn.execute(
                    """
                    INSERT INTO raw_holding_sections (section_name, broad_category)
                    VALUES (?, ?)
                    RETURNING section_id
                    """,
                    [sec_clean, broad_category],
                ).fetchone()[0]
            )

        self._section_cache[sec_clean] = sec_id
        return sec_id

    def get_or_create_instrument_id(
        self,
        instrument_name: str,
        isin: str | None,
        industry_or_rating: str | None,
    ) -> int:
        """Get or create instrument_id for instrument_name, isin, and industry/rating."""
        key = (instrument_name.strip(), isin, industry_or_rating)
        if key in self._instrument_cache:
            return self._instrument_cache[key]

        res = self.conn.execute(
            """
            SELECT instrument_id FROM raw_instrument_master
            WHERE instrument_name = ?
              AND (isin IS NOT DISTINCT FROM ?)
              AND (industry_or_rating IS NOT DISTINCT FROM ?)
            """,
            [key[0], isin, industry_or_rating],
        ).fetchone()

        if res:
            inst_id = int(res[0])
        else:
            inst_id = int(
                self.conn.execute(
                    """
                    INSERT INTO raw_instrument_master (instrument_name, isin, industry_or_rating)
                    VALUES (?, ?, ?)
                    RETURNING instrument_id
                    """,
                    [key[0], isin, industry_or_rating],
                ).fetchone()[0]
            )

        self._instrument_cache[key] = inst_id
        return inst_id

    def upsert_amc_master_absl(
        self,
        amc_sheet_name: str,
        amc_scheme_name: str,
        scheme_id: int | None,
        statement_date: date,
    ) -> None:
        """Update or insert into raw_amc_master_absl mapping table."""
        self.conn.execute(
            """
            INSERT INTO raw_amc_master_absl (amc_sheet_name, amc_scheme_name, scheme_id, last_statement_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (amc_sheet_name) DO UPDATE SET
                amc_scheme_name = EXCLUDED.amc_scheme_name,
                scheme_id = COALESCE(EXCLUDED.scheme_id, raw_amc_master_absl.scheme_id),
                last_statement_date = GREATEST(raw_amc_master_absl.last_statement_date, EXCLUDED.last_statement_date),
                insert_ts = now()
            """,
            [amc_sheet_name.strip(), amc_scheme_name.strip(), scheme_id, statement_date],
        )

    def save_statement(self, stmt: StatementMeta, overwrite: bool = True) -> int:
        """
        Save a statement header, its validated holdings, and any rejections.
        Returns the statement_id.
        """
        # Check if statement already exists
        existing = self.conn.execute(
            """
            SELECT statement_id FROM raw_portfolio_statement
            WHERE scheme_id = ? AND portfolio_date = ? AND frequency = ?
            """,
            [stmt.scheme_id, stmt.portfolio_date, stmt.frequency.value],
        ).fetchone()

        if existing:
            statement_id = int(existing[0])
            if not overwrite:
                logger.info(
                    "Statement for scheme_id %d on %s (%s) already exists (statement_id=%d). Skipping.",
                    stmt.scheme_id,
                    stmt.portfolio_date,
                    stmt.frequency.value,
                    statement_id,
                )
                return statement_id

            # If overwrite: remove old holdings and update statement
            self.conn.execute(
                "DELETE FROM raw_scheme_holdings WHERE statement_id = ?",
                [statement_id],
            )
            self.conn.execute(
                """
                UPDATE raw_portfolio_statement
                SET total_aum_lakhs = ?,
                    holding_count = ?,
                    rejected_count = ?,
                    source_file = ?,
                    insert_ts = now()
                WHERE statement_id = ?
                """,
                [
                    stmt.total_aum_lakhs,
                    len(stmt.holdings),
                    len(stmt.rejections),
                    stmt.source_file,
                    statement_id,
                ],
            )
        else:
            statement_id = int(
                self.conn.execute(
                    """
                    INSERT INTO raw_portfolio_statement (
                        fund_house_id, scheme_id, portfolio_date, frequency,
                        total_aum_lakhs, holding_count, rejected_count, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    RETURNING statement_id
                    """,
                    [
                        stmt.fund_house_id,
                        stmt.scheme_id,
                        stmt.portfolio_date,
                        stmt.frequency.value,
                        stmt.total_aum_lakhs,
                        len(stmt.holdings),
                        len(stmt.rejections),
                        stmt.source_file,
                    ],
                ).fetchone()[0]
            )

        stmt.statement_id = statement_id

        # Insert Holdings
        if stmt.holdings:
            rows_to_insert = []
            for h in stmt.holdings:
                sec_id = self.get_or_create_section_id(h.section_name, h.broad_category.value)
                inst_id = self.get_or_create_instrument_id(
                    h.instrument_name, h.isin, h.industry_or_rating
                )
                rows_to_insert.append(
                    (
                        statement_id,
                        sec_id,
                        inst_id,
                        h.quantity,
                        h.market_value_lakhs,
                        h.aum_pct,
                        h.ytm_pct,
                        h.ytc_pct,
                    )
                )

            self.conn.executemany(
                """
                INSERT INTO raw_scheme_holdings (
                    statement_id, section_id, instrument_id,
                    quantity, market_value_lakhs, aum_pct, ytm_pct, ytc_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )

        # Insert Rejections
        if stmt.rejections:
            rejections_to_insert = [
                (
                    r.amc,
                    r.scheme,
                    r.sheet_name,
                    r.line_number,
                    r.raw_row,
                    r.reason,
                    r.full_reason,
                )
                for r in stmt.rejections
            ]
            self.conn.executemany(
                """
                INSERT INTO raw_rejected_amc_holdings (
                    amc, scheme, sheet_name, line_number, raw_row, reason, full_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rejections_to_insert,
            )

        return statement_id
