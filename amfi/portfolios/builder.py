"""Materialises plans_portfolios and nav_portfolios tables."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl

from ..derived.views import NavFundsTable, NavPortfoliosTable, PlansFundsTable, PlansPortfoliosTable, TaxCategoryTable
from ..utils import LOGGER
from .config import PortfolioConfig

if TYPE_CHECKING:
    from ..db import Database

PORTFOLIO_ID_OFFSET = 9_000_000


class PortfolioBuilder:
    """Materialises ``plans_portfolios`` and ``nav_portfolios`` tables."""

    def __init__(self, db: Database, portfolios: list[PortfolioConfig]) -> None:
        self.db = db
        self.portfolios = portfolios

    def build(self) -> None:
        """Run plans + nav population. Safe when ``portfolios`` is empty."""
        if not self.portfolios:
            LOGGER.info("PORTFOLIO_BUILD_SKIP. No portfolios configured.")
            return

        LOGGER.info("PORTFOLIO_BUILD_START. count=%d", len(self.portfolios))
        self.build_plans()
        self.build_nav()
        LOGGER.info("PORTFOLIO_BUILD_SUCCESS.")

    def _constituent_aggregates(self, p: PortfolioConfig) -> dict[str, Any]:
        """Pull min aum, max launch_date, max start_date, min latest_date from plans_funds."""
        sd_ids = list(p.weights.keys())
        placeholders = ",".join("?" * len(sd_ids))
        row = self.db.conn.execute(
            f"""
            SELECT
                MIN(aum) AS aum,
                MAX(launch_date) AS launch_date,
                MAX(start_date) AS start_date,
                MIN(latest_date) AS latest_date
            FROM {PlansFundsTable.name()}
            WHERE sd_id IN ({placeholders})
            """,
            sd_ids,
        ).fetchone()
        if row is None:
            return {
                "aum": None,
                "launch_date": None,
                "start_date": None,
                "latest_date": None,
            }
        return {
            "aum": row[0],
            "launch_date": row[1],
            "start_date": row[2],
            "latest_date": row[3],
        }

    def _lookup_tax(self, category: str, subcategory: str) -> float | None:
        row = self.db.conn.execute(
            f"SELECT tax FROM {TaxCategoryTable.name()} "
            "WHERE category = ? AND subcategory = ?",
            [category, subcategory],
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return float(row[0])

    def build_plans(self) -> None:
        """Populate ``plans_portfolios`` with one row per configured portfolio."""
        rows: list[dict[str, Any]] = []
        for p in self.portfolios:
            agg = self._constituent_aggregates(p)
            if agg["start_date"] is None:
                LOGGER.warning(
                    "PORTFOLIO_SKIP. name=%r - no constituents found in plans_funds.",
                    p.name,
                )
                continue
            start_date = p.start_date or agg["start_date"]
            tax = self._lookup_tax(p.effective_category, p.effective_subcategory)
            rows.append(
                {
                    "fund_house_id": p.effective_fund_house_id,
                    "fund_house": p.effective_fund_house,
                    "scheme_id": p.synthetic_id,
                    "scheme": p.name,
                    "sd_id": p.synthetic_id,
                    "plan": p.name,
                    "scheme_type": "Open Ended",
                    "category": p.effective_category,
                    "subcategory": p.effective_subcategory,
                    "tax": tax,
                    "aum": agg["aum"],
                    "launch_date": agg["launch_date"],
                    "start_date": start_date,
                    "latest_date": agg["latest_date"],
                    "latest_nav": 100.0,
                    "is_in_use": True,
                    "is_not_lockin": True,
                    "is_retail": True,
                    "is_etf": True,
                    "is_growth": True,
                    "is_direct": True,
                }
            )

        table_name = PlansPortfoliosTable.name()
        self.db.conn.execute(f"DELETE FROM {table_name}")
        if not rows:
            LOGGER.info("PORTFOLIO_PLANS_EMPTY.")
            return

        df = pl.DataFrame(rows)
        self.db.conn.register("__plans_portfolios_tmp", df.to_arrow())
        try:
            self.db.conn.execute(
                f"""
                INSERT INTO {table_name}
                SELECT
                    CAST(fund_house_id AS INTEGER) AS fund_house_id,
                    CAST(fund_house AS VARCHAR)    AS fund_house,
                    CAST(scheme_id AS INTEGER)     AS scheme_id,
                    CAST(scheme AS VARCHAR)        AS scheme,
                    CAST(sd_id AS INTEGER)         AS sd_id,
                    CAST(plan AS VARCHAR)          AS plan,
                    CAST(scheme_type AS VARCHAR)   AS scheme_type,
                    CAST(category AS VARCHAR)      AS category,
                    CAST(subcategory AS VARCHAR)   AS subcategory,
                    CAST(tax AS DECIMAL(4,3))      AS tax,
                    CAST(aum AS DOUBLE)            AS aum,
                    CAST(launch_date AS DATE)      AS launch_date,
                    CAST(start_date AS DATE)       AS start_date,
                    CAST(latest_date AS DATE)      AS latest_date,
                    CAST(latest_nav AS DOUBLE)     AS latest_nav,
                    CAST(is_in_use AS BOOLEAN)     AS is_in_use,
                    CAST(is_not_lockin AS BOOLEAN) AS is_not_lockin,
                    CAST(is_retail AS BOOLEAN)     AS is_retail,
                    CAST(is_etf AS BOOLEAN)        AS is_etf,
                    CAST(is_growth AS BOOLEAN)     AS is_growth,
                    CAST(is_direct AS BOOLEAN)     AS is_direct
                FROM __plans_portfolios_tmp
                """
            )
        finally:
            self.db.conn.unregister("__plans_portfolios_tmp")
        LOGGER.info("PORTFOLIO_PLANS_WRITE. rows=%d", len(rows))

    def _portfolio_nav_series(self, p: PortfolioConfig) -> pl.DataFrame | None:
        """Compute (sd_id, date, nav, raw_nav) rows for portfolio ``p``."""
        sd_ids = list(p.weights.keys())
        placeholders = ",".join("?" * len(sd_ids))
        raw = self.db.conn.execute(
            f"""
            SELECT sd_id, date, nav
            FROM {NavFundsTable.name()}
            WHERE sd_id IN ({placeholders}) AND nav > 0
            """,
            sd_ids,
        ).pl()
        if raw.is_empty():
            LOGGER.warning(
                "PORTFOLIO_NAV_SKIP. name=%r - no nav_funds rows for constituents.",
                p.name,
            )
            return None

        wide = (
            raw.with_columns(pl.col("nav").cast(pl.Float64))
            .pivot(on="sd_id", index="date", values="nav")
            .sort("date")
        )
        cols = [str(sd) for sd in sd_ids]
        missing_cols = [c for c in cols if c not in wide.columns]
        if missing_cols:
            LOGGER.warning(
                "PORTFOLIO_NAV_SKIP. name=%r - constituents missing from nav_funds: %s",
                p.name,
                missing_cols,
            )
            return None
        wide = wide.drop_nulls(subset=cols)

        if p.start_date is not None:
            wide = wide.filter(pl.col("date") >= p.start_date)
        if wide.is_empty():
            LOGGER.warning(
                "PORTFOLIO_NAV_SKIP. name=%r - empty window after filters.",
                p.name,
            )
            return None

        first = wide.head(1)
        units = {sd: float(p.weights[sd]) / first[str(sd)].item() for sd in sd_ids}

        value_expr = pl.lit(0.0)
        for sd in sd_ids:
            value_expr = value_expr + pl.col(str(sd)) * units[sd]
        wide = wide.with_columns(_value=value_expr)

        base_value = wide["_value"].item(0)
        wide = wide.with_columns(
            nav=(pl.col("_value") / base_value * 100.0),
        )
        out = wide.select(
            pl.lit(p.synthetic_id, dtype=pl.Int32).alias("sd_id"),
            pl.col("date"),
            pl.col("nav").cast(pl.Float64),
            pl.col("nav").cast(pl.Float64).alias("raw_nav"),
        )
        return out

    def build_nav(self) -> None:
        """Populate ``nav_portfolios`` with concatenated per-portfolio series."""
        frames: list[pl.DataFrame] = []
        for p in self.portfolios:
            series = self._portfolio_nav_series(p)
            if series is not None:
                frames.append(series)
                start_date = series.get_column("date").min()
                LOGGER.info(
                    "PORTFOLIO_NAV. sd_id=%d name=%r start_date=%s",
                    p.synthetic_id,
                    p.name,
                    start_date,
                )

        table_name = NavPortfoliosTable.name()
        self.db.conn.execute(f"DELETE FROM {table_name}")
        if not frames:
            LOGGER.info("PORTFOLIO_NAV_EMPTY.")
            return

        combined = pl.concat(frames, how="vertical")
        self.db.conn.register("__nav_portfolios_tmp", combined.to_arrow())
        try:
            self.db.conn.execute(
                f"""
                INSERT INTO {table_name}
                SELECT
                    CAST(sd_id AS INTEGER) AS sd_id,
                    CAST(date AS DATE)     AS date,
                    CAST(nav AS DOUBLE)    AS nav,
                    CAST(raw_nav AS DOUBLE) AS raw_nav
                FROM __nav_portfolios_tmp
                """
            )
        finally:
            self.db.conn.unregister("__nav_portfolios_tmp")
        LOGGER.info("PORTFOLIO_NAV_WRITE. total_rows=%d", combined.height)
