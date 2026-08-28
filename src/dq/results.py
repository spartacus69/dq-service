"""Result objects.

Kept free of I/O so they can be asserted on in tests, serialised to JSON for a
metrics pipeline, or rendered for a human — without any of those concerns
leaking into the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from dq.rules import Severity


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Outcome of one rule against one dataset."""

    dataset: str
    table: str
    rule_name: str
    rule_type: str
    severity: Severity
    total_rows: int
    failed_rows: int
    threshold: float
    duration_ms: float
    error: str | None = None

    @property
    def failure_rate(self) -> float:
        if self.total_rows <= 0:
            return 0.0
        return self.failed_rows / self.total_rows

    @property
    def passed(self) -> bool:
        """A rule passes when it ran and stayed within its tolerance."""
        if self.error is not None:
            return False
        return self.failure_rate <= self.threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "table": self.table,
            "rule": self.rule_name,
            "type": self.rule_type,
            "severity": self.severity.value,
            "passed": self.passed,
            "total_rows": self.total_rows,
            "failed_rows": self.failed_rows,
            "failure_rate": round(self.failure_rate, 6),
            "threshold": self.threshold,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class SuiteResult:
    """Outcome of a whole run."""

    checks: list[CheckResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0

    @property
    def failed(self) -> list[CheckResult]:
        return [check for check in self.checks if not check.passed]

    @property
    def errors(self) -> list[CheckResult]:
        return [c for c in self.failed if c.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.failed if c.severity is Severity.WARN]

    @property
    def ok(self) -> bool:
        """True when nothing failed at ``error`` severity."""
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "duration_ms": round(self.duration_ms, 2),
            "summary": {
                "total": len(self.checks),
                "passed": len(self.checks) - len(self.failed),
                "failed": len(self.errors),
                "warned": len(self.warnings),
            },
            "checks": [check.to_dict() for check in self.checks],
        }


__all__ = ["CheckResult", "SuiteResult"]
