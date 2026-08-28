"""DuckDB implementation of the :class:`~dq.adapters.base.Adapter` port."""

from __future__ import annotations

import logging
from pathlib import Path
from types import TracebackType

import duckdb

from dq.errors import AdapterError

logger = logging.getLogger(__name__)


class DuckDBAdapter:
    """Runs compiled checks against a DuckDB database (file or in-memory)."""

    def __init__(self, database: str | Path = ":memory:", *, read_only: bool = False) -> None:
        target = str(database)
        try:
            self._con = duckdb.connect(target, read_only=read_only)
        except duckdb.Error as exc:  # pragma: no cover - depends on local fs
            raise AdapterError(f"cannot open DuckDB database {target!r}: {exc}") from exc
        logger.debug("connected to duckdb", extra={"database": target, "read_only": read_only})

    @property
    def name(self) -> str:
        return "duckdb"

    def quote(self, identifier: str) -> str:
        """Quote each dot-separated part: ``main.policies`` -> ``"main"."policies"``."""
        if not identifier.strip():
            raise AdapterError("identifier must not be empty")
        return ".".join(f'"{part.replace(chr(34), chr(34) * 2)}"' for part in identifier.split("."))

    def stale_predicate(self, column_expr: str, max_age_hours: int) -> str:
        hours = int(max_age_hours)
        return (
            f"(MAX({column_expr}) IS NULL "
            f"OR MAX({column_expr}) < CURRENT_TIMESTAMP - INTERVAL {hours} HOUR)"
        )

    def counts(self, sql: str) -> tuple[int, int]:
        try:
            row = self._con.execute(sql).fetchone()
        except duckdb.Error as exc:
            raise AdapterError(f"query failed: {exc}\n\n{sql}") from exc
        if row is None or len(row) < 2:
            raise AdapterError(f"check query returned no (total, failed) pair:\n\n{sql}")
        return int(row[0] or 0), int(row[1] or 0)

    def execute(self, sql: str) -> None:
        """Run a statement for its side effects — used by tests and seeding."""
        try:
            self._con.execute(sql)
        except duckdb.Error as exc:
            raise AdapterError(f"statement failed: {exc}\n\n{sql}") from exc

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> DuckDBAdapter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
