"""Orchestration: compile every rule, run it, collect the outcome.

One rule blowing up must not abort the run — a single malformed expression
would otherwise hide the state of every rule behind it. Failures are recorded
on the result and reported like any other violation.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from dq.adapters.base import Adapter
from dq.config import Dataset, Suite
from dq.errors import AdapterError
from dq.results import CheckResult, SuiteResult
from dq.rules import BaseRule

logger = logging.getLogger(__name__)


def run_rule(dataset: Dataset, rule: BaseRule, adapter: Adapter) -> CheckResult:
    """Run one rule and return its result, converting adapter failures into data."""
    started = time.perf_counter()
    common = {
        "dataset": dataset.name,
        "table": dataset.table,
        "rule_name": rule.name,
        "rule_type": getattr(rule, "type", rule.__class__.__name__),
        "severity": rule.severity,
        "threshold": rule.threshold,
    }
    try:
        sql = rule.to_sql(dataset.table, adapter)
        logger.debug("compiled rule %s: %s", rule.name, sql)
        total, failed = adapter.counts(sql)
    except AdapterError as exc:
        logger.warning("rule %s could not be evaluated: %s", rule.name, exc)
        return CheckResult(
            **common,  # type: ignore[arg-type]
            total_rows=0,
            failed_rows=0,
            duration_ms=(time.perf_counter() - started) * 1000,
            error=str(exc),
        )

    result = CheckResult(
        **common,  # type: ignore[arg-type]
        total_rows=total,
        failed_rows=failed,
        duration_ms=(time.perf_counter() - started) * 1000,
    )
    logger.info(
        "rule %s on %s: %s (%d/%d rows failed)",
        rule.name,
        dataset.table,
        "PASS" if result.passed else "FAIL",
        result.failed_rows,
        result.total_rows,
    )
    return result


def run_suite(suite: Suite, adapter: Adapter) -> SuiteResult:
    """Run every rule of every dataset in declaration order."""
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    checks: list[CheckResult] = []

    for dataset in suite.datasets:
        logger.debug("evaluating dataset %s (%s)", dataset.name, dataset.table)
        checks.extend(run_rule(dataset, rule, adapter) for rule in dataset.rules)

    return SuiteResult(
        checks=checks,
        started_at=started_at,
        duration_ms=(time.perf_counter() - started) * 1000,
    )


__all__ = ["run_rule", "run_suite"]
