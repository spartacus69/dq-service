"""Engine behaviour: thresholds, severities, and surviving a broken rule."""

from __future__ import annotations

from dq.config import Dataset, Suite
from dq.engine import run_rule, run_suite
from dq.results import CheckResult
from dq.rules import ExpressionRule, NotNullRule, Severity, UniqueRule


def dataset(*rules):  # noqa: ANN002 - test helper
    return Dataset(name="policies", table="policies", rules=list(rules))


def test_failing_rule_is_reported(adapter):
    rule = NotNullRule(type="not_null", name="pk", column="policy_id")
    result = run_rule(dataset(rule), rule, adapter)
    assert not result.passed
    assert result.failed_rows == 1
    assert result.total_rows == 8
    assert result.failure_rate == 0.125
    assert result.duration_ms >= 0


def test_threshold_tolerates_known_defects(adapter):
    rule = NotNullRule(type="not_null", name="pk", column="policy_id", threshold=0.2)
    result = run_rule(dataset(rule), rule, adapter)
    assert result.passed, "12.5% failures should pass a 20% threshold"


def test_threshold_boundary_is_inclusive(adapter):
    rule = NotNullRule(type="not_null", name="pk", column="policy_id", threshold=0.125)
    assert run_rule(dataset(rule), rule, adapter).passed


def test_broken_expression_does_not_abort_the_run(adapter):
    broken = ExpressionRule(type="expression", name="broken", expression="no_such_column > 1")
    healthy = NotNullRule(type="not_null", name="cust", column="customer_id")
    suite = Suite(datasets=[dataset(broken, healthy)])

    result = run_suite(suite, adapter)

    assert len(result.checks) == 2, "the healthy rule must still have been evaluated"
    assert result.checks[0].error is not None
    assert not result.checks[0].passed
    assert result.checks[1].passed


def test_suite_summary(adapter):
    suite = Suite(
        datasets=[
            dataset(
                NotNullRule(type="not_null", name="pk", column="policy_id"),
                NotNullRule(type="not_null", name="cust", column="customer_id"),
                UniqueRule(
                    type="unique", name="pk_unique", columns=["policy_id"], severity=Severity.WARN
                ),
            )
        ]
    )

    result = run_suite(suite, adapter)

    assert len(result.checks) == 3
    assert len(result.errors) == 1
    assert len(result.warnings) == 1
    assert not result.ok
    assert result.to_dict()["summary"] == {
        "total": 3,
        "passed": 1,
        "failed": 1,
        "warned": 1,
    }


def test_only_warnings_still_counts_as_ok(adapter):
    rule = UniqueRule(
        type="unique", name="pk_unique", columns=["policy_id"], severity=Severity.WARN
    )
    result = run_suite(Suite(datasets=[dataset(rule)]), adapter)
    assert result.ok, "warnings must not fail the run"
    assert result.failed


def test_rules_run_in_declaration_order(adapter):
    suite = Suite(
        datasets=[
            dataset(
                NotNullRule(type="not_null", name="first", column="policy_id"),
                NotNullRule(type="not_null", name="second", column="customer_id"),
            )
        ]
    )
    names = [check.rule_name for check in run_suite(suite, adapter).checks]
    assert names == ["first", "second"]


def test_failure_rate_of_empty_population_is_zero():
    check = CheckResult(
        dataset="d",
        table="t",
        rule_name="r",
        rule_type="not_null",
        severity=Severity.ERROR,
        total_rows=0,
        failed_rows=0,
        threshold=0.0,
        duration_ms=1.0,
    )
    assert check.failure_rate == 0.0
    assert check.passed
