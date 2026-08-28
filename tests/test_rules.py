"""Each rule type is exercised against real SQL, not against a mock.

Mocking the warehouse here would only prove that the string concatenation runs
— the interesting failures are dialect and NULL-handling bugs, which only a
real engine surfaces.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dq.rules import (
    AcceptedValuesRule,
    ExpressionRule,
    FreshnessRule,
    NotNullRule,
    RangeRule,
    RowCountRule,
    Severity,
    UniqueRule,
    sql_literal,
)

TABLE = "policies"


def counts(rule, adapter):
    return adapter.counts(rule.to_sql(TABLE, adapter))


class TestNotNull:
    def test_counts_the_single_null(self, adapter):
        total, failed = counts(NotNullRule(type="not_null", name="pk", column="policy_id"), adapter)
        assert (total, failed) == (8, 1)

    def test_clean_column_passes(self, adapter):
        _, failed = counts(NotNullRule(type="not_null", name="cust", column="customer_id"), adapter)
        assert failed == 0

    def test_empty_table_has_no_failures(self, empty_adapter):
        total, failed = counts(
            NotNullRule(type="not_null", name="pk", column="policy_id"), empty_adapter
        )
        assert (total, failed) == (0, 0)


class TestUnique:
    def test_duplicate_key_counts_both_rows(self, adapter):
        rule = UniqueRule(type="unique", name="pk_unique", columns=["policy_id"])
        total, failed = counts(rule, adapter)
        # The NULL policy_id is excluded from the population entirely.
        assert total == 7
        assert failed == 2

    def test_composite_key_is_unique(self, adapter):
        rule = UniqueRule(type="unique", name="pk2", columns=["policy_id", "customer_id"])
        _, failed = counts(rule, adapter)
        assert failed == 0


class TestAcceptedValues:
    def test_value_outside_domain_fails(self, adapter):
        rule = AcceptedValuesRule(
            type="accepted_values",
            name="status_domain",
            column="status",
            values=["active", "cancelled", "pending"],
        )
        total, failed = counts(rule, adapter)
        assert total == 8
        assert failed == 1

    def test_quotes_in_values_do_not_break_sql(self, adapter):
        rule = AcceptedValuesRule(
            type="accepted_values",
            name="quoted",
            column="status",
            values=["O'Brien", "active", "cancelled", "pending"],
        )
        _, failed = counts(rule, adapter)
        assert failed == 1


class TestRange:
    def test_negative_premium_fails(self, adapter):
        rule = RangeRule(type="range", name="premium_positive", column="premium_chf", min=0)
        _, failed = counts(rule, adapter)
        assert failed == 1

    def test_upper_bound(self, adapter):
        rule = RangeRule(type="range", name="premium_cap", column="premium_chf", max=1000)
        _, failed = counts(rule, adapter)
        assert failed == 1  # the 1200.00 policy

    def test_requires_a_bound(self):
        with pytest.raises(ValidationError, match="at least one of"):
            RangeRule(type="range", name="nope", column="premium_chf")

    def test_rejects_inverted_bounds(self):
        with pytest.raises(ValidationError, match="must not exceed"):
            RangeRule(type="range", name="nope", column="premium_chf", min=10, max=1)


class TestRowCount:
    def test_within_bounds(self, adapter):
        total, failed = counts(RowCountRule(type="row_count", name="rc", min=1, max=100), adapter)
        assert (total, failed) == (1, 0)

    def test_below_minimum(self, adapter):
        _, failed = counts(RowCountRule(type="row_count", name="rc", min=100), adapter)
        assert failed == 1

    def test_empty_table_fails_a_minimum(self, empty_adapter):
        _, failed = counts(RowCountRule(type="row_count", name="rc", min=1), empty_adapter)
        assert failed == 1


class TestFreshness:
    def test_recent_data_passes(self, adapter):
        rule = FreshnessRule(type="freshness", name="fresh", column="loaded_at", max_age_hours=24)
        total, failed = counts(rule, adapter)
        assert (total, failed) == (1, 0)

    def test_stale_data_fails(self, adapter):
        rule = FreshnessRule(type="freshness", name="stale", column="valid_from", max_age_hours=1)
        _, failed = counts(rule, adapter)
        assert failed == 1

    def test_empty_table_counts_as_stale(self, empty_adapter):
        rule = FreshnessRule(type="freshness", name="fresh", column="loaded_at", max_age_hours=24)
        _, failed = counts(rule, empty_adapter)
        assert failed == 1

    def test_rejects_non_positive_age(self):
        with pytest.raises(ValidationError):
            FreshnessRule(type="freshness", name="x", column="loaded_at", max_age_hours=0)


class TestExpression:
    def test_business_rule(self, adapter):
        rule = ExpressionRule(
            type="expression",
            name="cancelled_has_no_premium",
            expression="status <> 'cancelled' OR premium_chf = 0",
        )
        _, failed = counts(rule, adapter)
        assert failed == 0

    def test_null_result_counts_as_violation(self, adapter):
        rule = ExpressionRule(
            type="expression",
            name="null_expr",
            expression="policy_id IS NOT NULL AND policy_id <> ''",
        )
        _, failed = counts(rule, adapter)
        assert failed == 1


class TestRuleMetadata:
    def test_defaults(self):
        rule = NotNullRule(type="not_null", name="pk", column="policy_id")
        assert rule.severity is Severity.ERROR
        assert rule.threshold == 0.0

    def test_unknown_field_is_rejected(self):
        # mypy flags the typo statically; this asserts it is also caught at
        # runtime, which is what matters for a YAML file nobody type-checks.
        with pytest.raises(ValidationError):
            NotNullRule(type="not_null", name="pk", column="policy_id", colunm="typo")  # type: ignore[call-arg]

    def test_threshold_must_be_a_fraction(self):
        with pytest.raises(ValidationError):
            NotNullRule(type="not_null", name="pk", column="policy_id", threshold=1.5)

    def test_rules_are_immutable(self):
        rule = NotNullRule(type="not_null", name="pk", column="policy_id")
        with pytest.raises(ValidationError):
            rule.column = "other"  # type: ignore[misc]  # frozen model, by design


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("active", "'active'"),
        ("O'Brien", "'O''Brien'"),
        (42, "42"),
        (True, "TRUE"),
        (False, "FALSE"),
    ],
)
def test_sql_literal(value, expected):
    assert sql_literal(value) == expected


def test_identifier_quoting_survives_a_quote(adapter):
    assert adapter.quote('we"ird') == '"we""ird"'
    assert adapter.quote("main.policies") == '"main"."policies"'
