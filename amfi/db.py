from collections.abc import Sequence
from dataclasses import fields, is_dataclass
from datetime import date
from typing import Any

import duckdb

from .data import (
    RAW_TABLES,
    VIEWS,
    RawFundHouse,
    RawFundHouseResponse,
    RawNav,
    RawNavPlanDetails,
    RawNavPlanDetailsResponse,
    RawNavResponse,
    RawTable,
    T,
    View,
)
from .error import DatabaseExecutionError, DataValidationError
from .utils import LOGGER


class Database:
    def __init__(self, db_path: str):
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
        cursor = self._execute(sql, params, operation=operation)
        return cursor.fetchall()

    def _executemany(
        self,
        sql: str,
        params: list[list[Any]],
        *,
        operation: str,
    ) -> None:
        try:
            self.conn.executemany(sql, params)
        except duckdb.Error as exc:
            raise DatabaseExecutionError(
                operation=operation,
                sql=sql,
                params=None,
                cause=exc,
            ) from exc

    def create_raw(self, if_not_exists: bool = True, replace: bool = False) -> None:
        LOGGER.debug("CREATE_RAW_TABLES.")

        for table in RAW_TABLES:
            sql = table.create(if_not_exists=if_not_exists, replace=replace)
            self._execute(sql, operation=f"CREATE_RAW_{table.name().upper()}")

    def insert(self, table: RawTable[T], row: T) -> None:
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
        sql = table.existing_id_sql()
        rows = self._fetchall(
            sql, operation=f"SELECT_EXISTING_{table.name().upper()}_IDS"
        )
        return [str(row[0]) for row in rows if row and row[0] is not None]

    def get_missing_nav_dates(self) -> set[date]:
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

    def _create_view(self, view: type[View]) -> None:
        pre_check_sql = view.pre_check()
        if pre_check_sql:
            fail = self._fetchall(
                pre_check_sql, operation=f"PRE_CHECK_{view.name().upper()}"
            )
            if fail:
                raise DataValidationError(sql=pre_check_sql, failed_rows=fail)

        create_sql = view.create()
        self._execute(create_sql, operation=f"CREATE_VIEW_{view.name().upper()}")

    def create_views(self) -> None:
        for view in VIEWS:
            self._create_view(view)

    def close(self) -> None:
        self.conn.close()
