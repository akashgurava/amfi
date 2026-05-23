from collections.abc import Sequence
from dataclasses import fields, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from .data import (
    DEDUP_VIEWS,
    DERIVED_OBJECTS,
    METRICS_PERIOD_VIEWS,
    METRICS_TABLES,
    RAW_TABLES,
    MetricsConfig,
    RawFundHouse,
    RawFundHouseResponse,
    RawNav,
    RawNavPlanDetails,
    RawNavPlanDetailsResponse,
    RawNavResponse,
    RawTable,
    T,
)
from .error import DatabaseExecutionError
from .portfolios import PortfolioBuilder, load_portfolios
from .utils import LOGGER


class Database:
    """Thin DuckDB wrapper with typed helpers for raw tables and views."""

    def __init__(self, db_path: str):
        """Open (or create) a DuckDB database at ``db_path``."""
        self.db_path = db_path
        try:
            self.conn = duckdb.connect(db_path)
        except duckdb.Error as exc:
            raise RuntimeError(
                f"Failed to connect to DuckDB at {db_path!r}: {exc}"
            ) from exc

    def _execute(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        *,
        operation: str,
    ) -> duckdb.DuckDBPyConnection:
        """Helper to execute a SQL statement with optional parameters
        with error handling."""
        try:
            if params is None:
                return self.conn.execute(sql)
            return self.conn.execute(sql, params)
        except duckdb.Error as exc:
            raise DatabaseExecutionError(
                operation=operation,
                sql=sql,
                params=params,
                cause=exc,
            ) from exc

    def _fetchall(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        *,
        operation: str,
    ) -> list[tuple[Any, ...]]:
        """Helper to execute a SQL statement with optional parameters
        and fetch all results with error handling."""
        cursor = self._execute(sql, params, operation=operation)
        return cursor.fetchall()

    def _executemany(
        self,
        sql: str,
        params: list[list[Any]],
        *,
        operation: str,
    ) -> None:
        """Helper to execute a SQL statement with optional parameters
        and fetch all results with error handling."""
        try:
            self.conn.executemany(sql, params)
        except duckdb.Error as exc:
            raise DatabaseExecutionError(
                operation=operation,
                sql=sql,
                params=None,
                cause=exc,
            ) from exc

    def create_database_objects(
        self, if_not_exists: bool = True, replace: bool = False
    ) -> None:
        """Create all database objects (tables and views)."""
        LOGGER.debug("CREATE_DATABASE_OBJECTS_START.")

        LOGGER.debug("CREATE_RAW_TABLES")
        for table in RAW_TABLES:
            sql = table.create_sql(if_not_exists=if_not_exists, replace=replace)
            self._execute(sql, operation=f"CREATE_TABLE_{table.name().upper()}")

        LOGGER.debug("CREATE_DEDUP_VIEWS")
        for view in DEDUP_VIEWS:
            sql = view.create_sql()
            self._execute(sql, operation=f"CREATE_VIEW_{view.name().upper()}")

        LOGGER.debug("CREATE_DERIVED_OBJECTS")
        for obj in DERIVED_OBJECTS:
            sql = obj.create_sql(if_not_exists=if_not_exists, replace=replace)
            self._execute(sql, operation=f"CREATE_{obj.__name__.upper()}")

        LOGGER.debug("CREATE_METRICS_TABLES")
        for metrics_table in METRICS_TABLES:
            sql = metrics_table.create_sql(if_not_exists=if_not_exists, replace=replace)
            self._execute(sql, operation=f"CREATE_TABLE_{metrics_table.name().upper()}")

        LOGGER.debug("CREATE_METRICS_PERIOD_VIEWS")
        for period_view in METRICS_PERIOD_VIEWS:
            self._execute(
                period_view.create_sql(),
                operation=f"CREATE_VIEW_{period_view.name().upper()}",
            )

        LOGGER.debug("CREATE_DATABASE_OBJECTS_SUCCESS.")

    def insert(self, table: RawTable[T], row: T) -> None:
        """Insert a single dataclass row into ``table``.

        Validates that ``row`` is the expected dataclass type and that every
        value is a string (raw tables are all TEXT-typed).
        """
        expected_type = table.row_type()
        if not isinstance(row, expected_type):
            raise TypeError(
                f"Expected row type {expected_type.__name__} for {table.name()}, "
                f"got {type(row).__name__}"
            )

        if not is_dataclass(row):
            raise TypeError(f"Row for {table.name()} must be a dataclass instance")

        row_fields = {field.name for field in fields(row)}
        expected_fields = table.insert_columns()
        expected_fields_set = set(expected_fields)
        if row_fields != expected_fields_set:
            raise ValueError(
                f"Field mismatch for {table.name()}. "
                f"Expected {expected_fields}, got {tuple(row_fields)}"
            )

        params = [getattr(row, field_name) for field_name in expected_fields]
        if not all(isinstance(value, str) for value in params):
            raise TypeError(f"All values for {table.name()} must be strings: {params}")

        self._execute(
            table.insert_sql(),
            params,
            operation=f"INSERT_RAW_{table.name().upper()}",
        )

    def insert_fund_houses(self, fund_houses: Sequence[RawFundHouseResponse]) -> None:
        """Insert fund-house rows one-by-one into ``raw_fund_house``."""
        for fund_house in fund_houses:
            self.insert(RawFundHouse, fund_house)

    def bulk_insert_nav(self, rows: list[RawNavResponse]) -> None:
        """Bulk insert NAV rows using executemany.

        No deduplication — all rows are appended as-is.
        """
        if not rows:
            return
        columns = RawNav.insert_columns()
        sql = RawNav.insert_sql()
        params = [[getattr(row, col) for col in columns] for row in rows]
        self._executemany(sql, params, operation="BULK_INSERT_RAW_NAV")

    def insert_or_ignore_nav_plan_details(
        self, rows: list[RawNavPlanDetailsResponse]
    ) -> None:
        """Insert nav plan detail rows, silently skipping duplicates by sd_id."""
        if not rows:
            return
        columns = RawNavPlanDetails.insert_columns()
        sql = RawNavPlanDetails.insert_sql()
        params = [[getattr(row, col) for col in columns] for row in rows]
        self._executemany(
            sql, params, operation="INSERT_OR_IGNORE_RAW_NAV_PLAN_DETAILS"
        )

    def get_existing_raw_table_ids(self, table: type[RawTable[T]]) -> list[str]:
        """Return distinct primary-id values already persisted in ``table``."""
        sql = table.existing_id_sql()
        rows = self._fetchall(
            sql, operation=f"SELECT_EXISTING_{table.name().upper()}_IDS"
        )
        return [str(row[0]) for row in rows if row and row[0] is not None]

    def get_missing_nav_dates(self) -> set[date]:
        """Return dates in [2010-01-01, yesterday] with no rows in ``raw_nav``."""
        sql = """
        WITH date_series AS (
            select generate_series::date as date
            from generate_series(date '2010-01-01', current_date - 1, interval '1 day')
        )
        SELECT date FROM date_series
        EXCEPT
        SELECT hnav_date::date FROM raw_nav
        """
        rows = self._fetchall(sql, operation="SELECT_MISSING_NAV_DATES")
        return {row[0] for row in rows if row and row[0] is not None}

    def _build_derived_object(self, obj: type[Any]) -> None:
        """Populate one entry of :data:`DERIVED_OBJECTS`.

        Views (``DedupView`` / ``DerivedView``) are re-emitted with
        ``CREATE OR REPLACE VIEW`` so any body change propagates immediately.
        Derived tables are refilled via ``DELETE FROM + INSERT INTO`` against
        the pre-declared schema. Tables whose ``select_sql()`` raises
        :class:`NotImplementedError` are skipped - those are placeholders
        populated by external builders (e.g. :class:`PortfolioBuilder`).
        """
        name = obj.name()
        # Duck-type: DerivedTable subclasses define ``columns`` + ``select_sql``
        # + ``truncate``; Dedup/DerivedView do not have ``columns``. This
        # avoids runtime Protocol checks (DerivedTable is not decorated with
        # ``@runtime_checkable``).
        if hasattr(obj, "columns") and hasattr(obj, "select_sql"):
            try:
                select_sql = obj.select_sql()
            except NotImplementedError:
                LOGGER.debug(
                    "BUILD_DERIVED_SKIP. name=%s reason=externally_populated", name
                )
                return
            self._execute(obj.truncate(), operation=f"TRUNCATE_{name.upper()}")
            self._execute(
                f"INSERT INTO {name}\n{select_sql}",
                operation=f"INSERT_{name.upper()}",
            )
            LOGGER.debug("BUILD_DERIVED_TABLE. name=%s", name)
            return

        # View path: re-emit CREATE OR REPLACE VIEW.
        self._execute(obj.create_sql(), operation=f"CREATE_VIEW_{name.upper()}")
        LOGGER.debug("BUILD_DERIVED_VIEW. name=%s", name)

    def build(
        self,
        config_path: Path | None = None,
        metrics_config: MetricsConfig | None = None,
    ) -> None:
        """Populate the full derived + metrics stack.

        Pure-insert pipeline that assumes schemas are already in place via
        :meth:`create_database_objects` (called by :meth:`App.init_db`).
        Order:

        1. For each :data:`DERIVED_OBJECTS` entry: re-emit views /
           truncate+insert derived tables. Placeholder tables populated by
           external builders are skipped here.
        2. :meth:`build_portfolios` fills ``plans_portfolios`` /
           ``nav_portfolios`` when ``config_path`` is provided.
        3. :meth:`build_metrics` fills every ``metrics_*`` table and emits
           the per-period views.
        """
        LOGGER.info("BUILD_START. derived=%s", [o.name() for o in DERIVED_OBJECTS])
        for obj in DERIVED_OBJECTS:
            self._build_derived_object(obj)
        self.build_portfolios(config_path)
        self.build_metrics(metrics_config)
        LOGGER.info("BUILD_SUCCESS.")

    def build_portfolios(self, config_path: Path | None) -> None:
        """Populate ``plans_portfolios`` + ``nav_portfolios`` from a YAML file.

        Imported lazily; a missing ``config_path`` or missing file leaves the
        empty placeholder tables in place.
        """
        if config_path is None:
            LOGGER.info("BUILD_PORTFOLIOS_SKIP. No config path provided.")
            return

        portfolios = load_portfolios(config_path)
        PortfolioBuilder(self, portfolios).build()

    def build_metrics(
        self,
        config: MetricsConfig | None = None,
        benchmark_sd_id: int = 120716,
    ) -> None:
        """Recompute the ``metrics_*`` tables from current ``nav`` + ``plans``.

        Imported lazily to avoid a hard dependency on polars for callers that
        only need raw fetches.
        """
        from .metrics import DatabaseMetricsAdapter

        DatabaseMetricsAdapter(
            self, benchmark_sd_id=benchmark_sd_id, config=config
        ).build()

    def close(self) -> None:
        """Close the underlying DuckDB connection."""
        self.conn.close()
