from typing import Any, Protocol, TypeVar

from ..error import AppConfigError

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)


class Buildable(Protocol):
    """
    Minimal protocol for database objects that can be built.
    """

    @classmethod
    def name(cls) -> str:
        """Name of the database object."""
        ...

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        """Create SQL for the database object."""
        ...


class Table(Buildable, Protocol):
    """Protocol for database tables."""


class RawTable(Table, Protocol[T_co]):
    """
    Protocol for raw database tables.
    """

    @classmethod
    def row_type(cls) -> type[T_co]:
        """Row type of the table."""
        ...

    @classmethod
    def id_columns(cls) -> tuple[str, ...]:
        """
        Columns that uniquely identify a row in the table.
        For raw tables this is usually just a combination of cid columns.
        """
        ...

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        """
        Create SQL for the raw table.

        Args:
            if_not_exists: If True, the table will be created if it doesn't exist.
            replace: If True, the table will be replaced if it exists.

        Returns:
            Create SQL for the table.
        """
        if if_not_exists and replace:
            raise AppConfigError(
                "if_not_exists and replace",
                "BOTH_CANNOT_BE_TRUE",
                (if_not_exists, replace),
            )

        if replace:
            prefix = "OR REPLACE TABLE"
        else:
            if if_not_exists:
                prefix = "TABLE IF NOT EXISTS"
            else:
                prefix = "TABLE"

        return f"""
            CREATE {prefix} {cls.name()} (
                {cls.column_definitions()}
                loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """

    @classmethod
    def column_definitions(cls) -> str:
        """
        Column definitions for the table used while creating the table.
        Usually looks like
        ```sql
        id TEXT NOT NULL PRIMARY KEY,
        name TEXT NOT NULL
        ```
        """
        ...

    @classmethod
    def insert_columns(cls) -> tuple[str, ...]:
        """
        Columns orderd as per their insert order.
        Usually looks like
        ```python
        ("id", "name")
        ```
        """
        ...

    @classmethod
    def insert_sql(cls) -> str:
        columns = cls.insert_columns()
        placeholders = ", ".join(["?"] * len(columns))
        columns_sql = ", ".join(columns)
        return f"INSERT INTO {cls.name()} ({columns_sql}) VALUES ({placeholders})"

    @classmethod
    def existing_id_sql(cls) -> str:
        id_columns = cls.id_columns()
        return f"SELECT DISTINCT {', '.join(id_columns)} FROM {cls.name()}"


class View(Buildable, Protocol):
    """Minimal protocol for views the :class:`Database` can build.

    Concrete kinds are :class:`DedupView` (single-source dedup-by-``loaded_at``,
    materialised as a ``VIEW``), :class:`DerivedView` (arbitrary SQL body,
    materialised as a ``VIEW``), and :class:`DerivedTable` (explicit column
    DDL, materialised as a ``TABLE`` populated via truncate+insert).
    """

    @classmethod
    def name(cls) -> str:
        """Name of the view/table in the database."""
        ...

    @classmethod
    def pre_check(cls) -> str | None:
        """SQL returning rows if data is invalid. ``None`` skips the check."""
        ...

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        """SQL that builds or replaces this view/table."""
        ...


class DedupView(View, Protocol):
    """View on top of RawTables to get latest data(by loaded_at)
    for each :meth:`id_columns`.
    """

    @classmethod
    def name(cls) -> str:
        """Name of the view."""
        ...

    @classmethod
    def source_table(cls) -> type[RawTable[Any]]:
        """Raw table that the view reads from."""
        ...

    @classmethod
    def id_columns(cls) -> tuple[str, ...]:
        """Columns to partition by when deduplicating by ``loaded_at``."""
        ...

    @classmethod
    def column_definitions(cls) -> str:
        """SELECT list expressions (comma-separated, trailing comma not needed)."""
        ...

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        return f"""
        CREATE OR REPLACE VIEW {cls.name()} AS
        SELECT {cls.column_definitions()} FROM {cls.source_table().name()}
        QUALIFY ROW_NUMBER()
            OVER (PARTITION BY {",".join(cls.id_columns())} ORDER BY loaded_at DESC) = 1
        """


class DerivedView(View, Protocol):
    """View defined by an arbitrary SELECT body (multi-source joins, etc.)."""

    @classmethod
    def select_sql(cls) -> str:
        """The SQL body that follows ``CREATE OR REPLACE VIEW name AS``."""
        ...

    @classmethod
    def pre_check(cls) -> str | None:
        return None

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        return f"CREATE OR REPLACE VIEW {cls.name()} AS\n{cls.select_sql()}"


class DerivedTable(Table, Protocol):
    """Materialised table with an explicit column schema.

    Subclasses declare their column DDL via :meth:`columns` so the table is
    created once at :meth:`Database.create_database_objects` time and
    repopulated on every build via ``DELETE FROM ...; INSERT INTO ...
    <select_sql>``. This mirrors the ``raw_*`` pattern and keeps the
    relation kind stable across runs (no table-vs-view oscillation).
    """

    @classmethod
    def columns(cls) -> str:
        """Column DDL fragment (e.g. ``"sd_id INTEGER, date DATE, nav DOUBLE"``)."""
        ...

    @classmethod
    def select_sql(cls) -> str:
        """SQL body used to (re)populate this table during build.

        Subclasses whose table is populated by an external builder (e.g.
        portfolio placeholders) should raise :class:`NotImplementedError` so
        the generic build loop in :meth:`Database.build` knows to skip them.
        """
        ...

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        """``CREATE TABLE`` wrapping :meth:`columns`.

        Mirrors :meth:`RawTable.create_sql`'s ``if_not_exists`` / ``replace``
        semantics so :meth:`Database.create_database_objects` can dispatch
        uniformly across every :class:`Buildable`.
        """
        if if_not_exists and replace:
            raise AppConfigError(
                "if_not_exists and replace",
                "BOTH_CANNOT_BE_TRUE",
                (if_not_exists, replace),
            )
        if replace:
            prefix = "OR REPLACE TABLE"
        elif if_not_exists:
            prefix = "TABLE IF NOT EXISTS"
        else:
            prefix = "TABLE"
        return f"CREATE {prefix} {cls.name()} ({cls.columns()})"

    @classmethod
    def truncate(cls) -> str:
        return f"DELETE FROM {cls.name()}"

    @classmethod
    def insert_sql(cls) -> str:
        """``INSERT INTO`` statement fed by :meth:`select_sql`."""
        return f"INSERT INTO {cls.name()}\n{cls.select_sql()}"
