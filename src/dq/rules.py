"""Rule types and their compilation to SQL.

Every rule compiles to a query returning exactly two columns::

    total_rows   the population the rule was evaluated against
    failed_rows  how many of them violate it

That uniform shape is what keeps the engine free of per-rule branching, and it
is what lets a rule expressed in YAML behave exactly like one written by hand.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dq.adapters.base import Adapter

ScalarValue = str | int | float | bool


class Severity(str, Enum):
    """How much a violation matters."""

    ERROR = "error"
    WARN = "warn"


def sql_literal(value: ScalarValue) -> str:
    """Render a Python scalar as a SQL literal, escaping single quotes."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + value.replace("'", "''") + "'"


class BaseRule(BaseModel, ABC):
    """Fields shared by every rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="Unique, stable identifier of the rule.")
    severity: Severity = Severity.ERROR
    threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Tolerated share of failing rows, 0.0 = zero tolerance.",
    )
    description: str | None = None

    @abstractmethod
    def to_sql(self, table: str, adapter: Adapter) -> str:
        """Compile the rule into a ``(total_rows, failed_rows)`` query."""

    def _wrap(self, table: str, adapter: Adapter, fail_expr: str, where: str = "") -> str:
        """Row-level rules share this shape: count rows, count the bad ones."""
        clause = f" WHERE {where}" if where else ""
        return (
            "SELECT COUNT(*) AS total_rows, "
            f"COALESCE(SUM(CASE WHEN {fail_expr} THEN 1 ELSE 0 END), 0) AS failed_rows "
            f"FROM {adapter.quote(table)}{clause}"
        )


class NotNullRule(BaseRule):
    """The column must be populated on every row."""

    type: Literal["not_null"]
    column: str = Field(min_length=1)

    def to_sql(self, table: str, adapter: Adapter) -> str:
        return self._wrap(table, adapter, f"{adapter.quote(self.column)} IS NULL")


class UniqueRule(BaseRule):
    """The column combination must identify at most one row.

    Rows where any key column is NULL are excluded: SQL treats NULLs as
    distinct, so counting them as duplicates would be misleading. Catch those
    with a ``not_null`` rule instead.
    """

    type: Literal["unique"]
    columns: list[str] = Field(min_length=1)

    def to_sql(self, table: str, adapter: Adapter) -> str:
        cols = [adapter.quote(col) for col in self.columns]
        key = ", ".join(cols)
        not_null = " AND ".join(f"{col} IS NOT NULL" for col in cols)
        return (
            "SELECT COALESCE(SUM(group_size), 0) AS total_rows, "
            "COALESCE(SUM(CASE WHEN group_size > 1 THEN group_size ELSE 0 END), 0) AS failed_rows "
            "FROM (SELECT COUNT(*) AS group_size "
            f"FROM {adapter.quote(table)} WHERE {not_null} GROUP BY {key}) AS dq_groups"
        )


class AcceptedValuesRule(BaseRule):
    """The column may only contain values from a known domain."""

    type: Literal["accepted_values"]
    column: str = Field(min_length=1)
    values: list[ScalarValue] = Field(min_length=1)

    def to_sql(self, table: str, adapter: Adapter) -> str:
        col = adapter.quote(self.column)
        domain = ", ".join(sql_literal(value) for value in self.values)
        return self._wrap(table, adapter, f"{col} NOT IN ({domain})", where=f"{col} IS NOT NULL")


class RangeRule(BaseRule):
    """The column must stay within numeric bounds."""

    type: Literal["range"]
    column: str = Field(min_length=1)
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _check_bounds(self) -> RangeRule:
        if self.min is None and self.max is None:
            raise ValueError("range rule needs at least one of 'min' or 'max'")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"min ({self.min}) must not exceed max ({self.max})")
        return self

    def to_sql(self, table: str, adapter: Adapter) -> str:
        col = adapter.quote(self.column)
        conditions: list[str] = []
        if self.min is not None:
            conditions.append(f"{col} < {self.min}")
        if self.max is not None:
            conditions.append(f"{col} > {self.max}")
        return self._wrap(table, adapter, " OR ".join(conditions), where=f"{col} IS NOT NULL")


class RowCountRule(BaseRule):
    """The table as a whole must contain a plausible number of rows.

    This is a table-level rule: it reports a single observation, so
    ``total_rows`` is 1 and ``threshold`` has no useful meaning.
    """

    type: Literal["row_count"]
    min: int | None = Field(default=None, ge=0)
    max: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_bounds(self) -> RowCountRule:
        if self.min is None and self.max is None:
            raise ValueError("row_count rule needs at least one of 'min' or 'max'")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"min ({self.min}) must not exceed max ({self.max})")
        return self

    def to_sql(self, table: str, adapter: Adapter) -> str:
        conditions: list[str] = []
        if self.min is not None:
            conditions.append(f"observed < {self.min}")
        if self.max is not None:
            conditions.append(f"observed > {self.max}")
        fail_expr = " OR ".join(conditions)
        return (
            "SELECT 1 AS total_rows, "
            f"CASE WHEN {fail_expr} THEN 1 ELSE 0 END AS failed_rows "
            f"FROM (SELECT COUNT(*) AS observed FROM {adapter.quote(table)}) AS dq_count"
        )


class FreshnessRule(BaseRule):
    """The newest timestamp in the table must be recent enough.

    Table-level, like :class:`RowCountRule`. An empty table counts as stale.
    """

    type: Literal["freshness"]
    column: str = Field(min_length=1)
    max_age_hours: int = Field(gt=0)

    def to_sql(self, table: str, adapter: Adapter) -> str:
        col = adapter.quote(self.column)
        predicate = adapter.stale_predicate(col, self.max_age_hours)
        return (
            "SELECT 1 AS total_rows, "
            f"CASE WHEN {predicate} THEN 1 ELSE 0 END AS failed_rows "
            f"FROM {adapter.quote(table)}"
        )


class ExpressionRule(BaseRule):
    """An arbitrary boolean SQL expression that must hold for every row.

    The escape hatch for business rules the built-in types do not cover, e.g.
    ``premium_amount >= 0 OR status = 'cancelled'``.

    The expression is inlined into the generated SQL verbatim. Rule files are
    therefore trusted input, at the same level as application code — review
    them the way you review a pull request, and never accept them from an
    untrusted source.
    """

    type: Literal["expression"]
    expression: str = Field(min_length=1)

    def to_sql(self, table: str, adapter: Adapter) -> str:
        # NULL is not TRUE, so a NULL result counts as a violation.
        return self._wrap(table, adapter, f"COALESCE(({self.expression}), FALSE) = FALSE")


Rule = Annotated[
    NotNullRule
    | UniqueRule
    | AcceptedValuesRule
    | RangeRule
    | RowCountRule
    | FreshnessRule
    | ExpressionRule,
    Field(discriminator="type"),
]

__all__ = [
    "AcceptedValuesRule",
    "BaseRule",
    "ExpressionRule",
    "FreshnessRule",
    "NotNullRule",
    "RangeRule",
    "RowCountRule",
    "Rule",
    "Severity",
    "UniqueRule",
    "sql_literal",
]
