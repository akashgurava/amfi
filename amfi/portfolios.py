"""Config-driven synthetic portfolios.

A ``config.yml`` at the repo root (or any path passed via ``--config``) lists
user-defined portfolios. Each portfolio is materialised into two tables so
downstream code (``plans``, ``nav``, and therefore every ``metrics_*``
table) sees them uniformly with real AMFI funds:

- ``plans_portfolios`` - one row per portfolio, same column layout as
  ``plans_funds``. Populated by :meth:`PortfolioBuilder.build_plans`.
- ``nav_portfolios`` - daily normalised NAV series per portfolio (starts at
  100 on the portfolio's first date). Populated by
  :meth:`PortfolioBuilder.build_nav`.

The ``plans`` and ``nav`` SQL objects remain ``UNION ALL`` views over the
``*_funds`` and ``*_portfolios`` tables (see :mod:`amfi.data`).

Expected YAML shape::

    portfolios:
      HDFC All Cap Conservative:
        fund_house_id: 9            # optional
        fund_house: HDFC            # optional; defaults to portfolio name
        category: other             # optional; default "equity"
        subcategory: index funds    # optional; default "multi cap"
        start_date: '2025-01-01'    # optional; default latest constituent first_date
        weights:
          149870: 50000             # sd_id -> rupees invested at start_date
          151724: 30000
          151727: 20000

Synthetic IDs
-------------
Portfolios get deterministic IDs derived from their 0-based index in the
YAML mapping: ``sd_id = scheme_id = 9_000_000 + index + 1`` and
``fund_house_id = config value or 9_000_000 + index + 1``. The ``+ 1`` makes
the first portfolio land on ``9_000_001``, which reads more naturally in
filters (``sd_id >= 9_000_001``). All IDs stay well above the ~200k range
of real AMFI IDs.

Missing-date policy
-------------------
For each portfolio we inner-join constituent NAV series on ``date``, so
only dates where *every* constituent has a NAV row produce a portfolio NAV.
The window runs from ``config.start_date`` (or ``max(constituent.first_date)``
if omitted) to ``min(constituent.last_date)``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as date_t
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import yaml

from .data import (
    NavFundsTable,
    NavPortfoliosTable,
    PlansFundsTable,
    PlansPortfoliosTable,
    TaxCategoryTable,
)
from .error import AppConfigError

if TYPE_CHECKING:
    from .db import Database

LOGGER = logging.getLogger(__name__)

PORTFOLIO_ID_OFFSET = 9_000_000


@dataclass(frozen=True)
class PortfolioConfig:
    """Parsed portfolio definition.

    ``index`` is the 0-based position in the YAML mapping, used to derive
    deterministic synthetic IDs (``PORTFOLIO_ID_OFFSET + index + 1`` — the
    ``+ 1`` shifts the first portfolio to ``9_000_001`` for cleaner filters).
    """

    name: str
    index: int
    weights: dict[int, float]
    fund_house_id: int | None = None
    fund_house: str | None = None
    category: str | None = None
    subcategory: str | None = None
    start_date: date_t | None = None

    @property
    def sd_id(self) -> int:
        return PORTFOLIO_ID_OFFSET + self.index + 1

    @property
    def scheme_id(self) -> int:
        return PORTFOLIO_ID_OFFSET + self.index + 1

    @property
    def effective_fund_house_id(self) -> int:
        return (
            self.fund_house_id
            if self.fund_house_id is not None
            else PORTFOLIO_ID_OFFSET + self.index + 1
        )

    @property
    def effective_fund_house(self) -> str:
        return self.fund_house if self.fund_house is not None else self.name

    @property
    def effective_category(self) -> str:
        return self.category if self.category is not None else "equity"

    @property
    def effective_subcategory(self) -> str:
        return self.subcategory if self.subcategory is not None else "multi cap"


def load_portfolios(path: Path) -> list[PortfolioConfig]:
    """Load and validate ``path`` (YAML). Returns ``[]`` if file is absent.

    Raises :class:`AppConfigError` on malformed structure.
    """
    if not path.exists():
        LOGGER.info("PORTFOLIO_LOAD_SKIP. path=%s absent.", path)
        return []

    with path.open() as fh:
        raw = yaml.safe_load(fh) or {}

    portfolios_block = raw.get("portfolios")
    if portfolios_block is None:
        return []
    if not isinstance(portfolios_block, dict):
        raise AppConfigError(
            "portfolios", "MUST_BE_MAPPING", type(portfolios_block).__name__
        )

    out: list[PortfolioConfig] = []
    for idx, (name, body) in enumerate(portfolios_block.items()):
        if not isinstance(name, str) or not name.strip():
            raise AppConfigError("portfolio name", "MUST_BE_NONEMPTY_STRING", name)
        if not isinstance(body, dict):
            raise AppConfigError(
                f"portfolios[{name!r}]", "MUST_BE_MAPPING", type(body).__name__
            )

        weights_raw = body.get("weights")
        if not isinstance(weights_raw, dict) or not weights_raw:
            raise AppConfigError(
                f"portfolios[{name!r}].weights",
                "MUST_BE_NONEMPTY_MAPPING",
                weights_raw,
            )
        weights: dict[int, float] = {}
        for sd_key, amount in weights_raw.items():
            try:
                sd_id = int(sd_key)
            except (TypeError, ValueError) as e:
                raise AppConfigError(
                    f"portfolios[{name!r}].weights key", "MUST_BE_INT", sd_key
                ) from e
            if not isinstance(amount, (int, float)) or amount <= 0:
                raise AppConfigError(
                    f"portfolios[{name!r}].weights[{sd_id}]",
                    "MUST_BE_POSITIVE_NUMBER",
                    amount,
                )
            weights[sd_id] = float(amount)

        start_raw = body.get("start_date")
        start_date: date_t | None
        if start_raw is None:
            start_date = None
        elif isinstance(start_raw, date_t):
            start_date = start_raw
        elif isinstance(start_raw, str):
            start_date = date_t.fromisoformat(start_raw)
        else:
            raise AppConfigError(
                f"portfolios[{name!r}].start_date",
                "MUST_BE_DATE_OR_ISO_STRING",
                start_raw,
            )

        fund_house_id_raw = body.get("fund_house_id")
        if fund_house_id_raw is not None and not isinstance(fund_house_id_raw, int):
            raise AppConfigError(
                f"portfolios[{name!r}].fund_house_id",
                "MUST_BE_INT",
                fund_house_id_raw,
            )

        out.append(
            PortfolioConfig(
                name=name,
                index=idx,
                weights=weights,
                fund_house_id=fund_house_id_raw,
                fund_house=body.get("fund_house"),
                category=body.get("category"),
                subcategory=body.get("subcategory"),
                start_date=start_date,
            )
        )
    LOGGER.info("PORTFOLIO_LOAD_SUCCESS. path=%s count=%d", path, len(out))
    return out


class PortfolioBuilder:
    """Materialises ``plans_portfolios`` and ``nav_portfolios`` tables."""

    def __init__(self, db: Database, portfolios: list[PortfolioConfig]) -> None:
        self.db = db
        self.portfolios = portfolios

    def build(self) -> None:
        """Run plans + nav population. Safe when ``portfolios`` is empty."""
        if not self.portfolios:
            LOGGER.info("PORTFOLIO_BUILD_SKIP. No portfolios configured.")
            # Ensure the two tables exist with the right schema even when no
            # portfolios are defined; the DerivedTable framework already
            # created them as empty ``SELECT * FROM *_funds WHERE FALSE``.
            return

        LOGGER.info("PORTFOLIO_BUILD_START. count=%d", len(self.portfolios))
        self.build_plans()
        self.build_nav()
        LOGGER.info("PORTFOLIO_BUILD_SUCCESS.")

    def _constituent_aggregates(self, p: PortfolioConfig) -> dict[str, Any]:
        """Pull min aum, max launch_date, max start_date, min latest_date from
        ``plans_funds`` for the portfolio's constituent ``sd_id``s.
        """
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
                    "scheme_id": p.scheme_id,
                    "scheme": p.name,
                    "sd_id": p.sd_id,
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

        # Truncate-and-load into the pre-declared schema. Columns match
        # :data:`amfi.data._PLANS_FUNDS_COLUMNS`; casts ensure the INSERT
        # SELECT types line up exactly with DuckDB's column types.
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
        """Compute (sd_id, date, nav, raw_nav) rows for portfolio ``p``.

        Returns ``None`` if the portfolio has no window with all constituents
        present. Uses split-adjusted ``nav_funds`` so the portfolio inherits
        consistent handling with metrics inputs.
        """
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

        # Pivot to wide: one column per constituent, sorted by date.
        wide = (
            raw.with_columns(pl.col("nav").cast(pl.Float64))
            .pivot(on="sd_id", index="date", values="nav")
            .sort("date")
        )
        # Inner join semantics: drop rows where any constituent is missing.
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

        # Units per constituent at window start. Constant through the series.
        first = wide.head(1)
        units = {sd: float(p.weights[sd]) / first[str(sd)].item() for sd in sd_ids}

        # Portfolio value per date.
        value_expr = pl.lit(0.0)
        for sd in sd_ids:
            value_expr = value_expr + pl.col(str(sd)) * units[sd]
        wide = wide.with_columns(_value=value_expr)

        base_value = wide["_value"].item(0)
        wide = wide.with_columns(
            nav=(pl.col("_value") / base_value * 100.0),
        )
        out = wide.select(
            pl.lit(p.sd_id, dtype=pl.Int32).alias("sd_id"),
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
                # Log the portfolio identity + effective start_date instead
                # of the raw row count; downstream filters use sd_id, so
                # surfacing it in the log speeds up incident triage.
                start_date = series.get_column("date").min()
                LOGGER.info(
                    "PORTFOLIO_NAV. sd_id=%d name=%r start_date=%s",
                    p.sd_id,
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


__all__ = [
    "PORTFOLIO_ID_OFFSET",
    "PortfolioBuilder",
    "PortfolioConfig",
    "load_portfolios",
]
