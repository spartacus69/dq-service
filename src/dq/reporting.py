"""Rendering results for humans and for machines."""

from __future__ import annotations

import json

from dq.results import SuiteResult
from dq.rules import Severity

_MARK = {True: "PASS", False: "FAIL"}


def format_text(result: SuiteResult, *, verbose: bool = False) -> str:
    """A compact report: failures always, passes only when asked."""
    lines: list[str] = []
    for check in result.checks:
        if check.passed and not verbose:
            continue
        marker = _MARK[check.passed]
        if not check.passed and check.severity is Severity.WARN:
            marker = "WARN"
        detail = (
            f"{check.failed_rows}/{check.total_rows} rows"
            if check.error is None
            else f"not evaluated: {check.error.splitlines()[0]}"
        )
        lines.append(
            f"  [{marker}] {check.dataset}.{check.rule_name} ({check.rule_type}) — {detail}"
        )

    summary = result.to_dict()["summary"]
    header = (
        f"{summary['total']} checks · {summary['passed']} passed · "
        f"{summary['failed']} failed · {summary['warned']} warnings "
        f"({result.duration_ms:.0f} ms)"
    )
    if not lines:
        return f"{header}\n  all checks passed"
    return "\n".join([header, *lines])


def format_json(result: SuiteResult) -> str:
    """Machine-readable output, suitable for piping into a metrics sink."""
    return json.dumps(result.to_dict(), indent=2, sort_keys=False)


__all__ = ["format_json", "format_text"]
