"""The port through which the engine talks to a warehouse.

Rules compile to SQL but must not know which warehouse runs it. Everything
dialect-specific lives behind this Protocol, so adding BigQuery means adding
one class here — not touching a single rule.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Adapter(Protocol):
    """Minimal surface a warehouse must offer to run quality checks."""

    @property
    def name(self) -> str:
        """Short identifier of the backend, e.g. ``duckdb``."""
        ...

    def quote(self, identifier: str) -> str:
        """Quote a possibly dotted identifier (``schema.table``) for this dialect."""
        ...

    def stale_predicate(self, column_expr: str, max_age_hours: int) -> str:
        """Return a boolean SQL aggregate that is true when the data is stale.

        Must also evaluate to true for an empty table: no rows at all is the
        most severe form of staleness, and a silent pass would hide it.
        """
        ...

    def counts(self, sql: str) -> tuple[int, int]:
        """Run a compiled check and return ``(total_rows, failed_rows)``."""
        ...

    def close(self) -> None:
        """Release the underlying connection."""
        ...
