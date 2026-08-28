"""Config loading: the error messages matter as much as the happy path."""

from __future__ import annotations

import pytest

from dq.config import load_suite
from dq.errors import ConfigError
from dq.rules import NotNullRule, Severity

VALID = """
version: 1
datasets:
  - name: policies
    table: policies
    rules:
      - name: policy_id_not_null
        type: not_null
        column: policy_id
      - name: status_domain
        type: accepted_values
        column: status
        values: [active, cancelled, pending]
        severity: warn
        threshold: 0.05
"""


def write(tmp_path, text, filename="rules.yml"):
    path = tmp_path / filename
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_a_valid_suite(tmp_path):
    suite = load_suite(write(tmp_path, VALID))
    assert suite.rule_count == 2
    assert isinstance(suite.datasets[0].rules[0], NotNullRule)
    assert suite.datasets[0].rules[1].severity is Severity.WARN
    assert suite.datasets[0].rules[1].threshold == 0.05


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_suite(tmp_path / "nope.yml")


def test_invalid_yaml(tmp_path):
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_suite(write(tmp_path, "datasets: [\n  - unclosed"))


def test_top_level_must_be_a_mapping(tmp_path):
    with pytest.raises(ConfigError, match="mapping"):
        load_suite(write(tmp_path, "- just\n- a\n- list\n"))


def test_unknown_rule_type_is_rejected(tmp_path):
    text = VALID.replace("type: not_null", "type: teleportation")
    with pytest.raises(ConfigError, match="failed validation"):
        load_suite(write(tmp_path, text))


def test_typo_in_field_name_is_rejected(tmp_path):
    text = VALID.replace("column: policy_id", "colunm: policy_id")
    with pytest.raises(ConfigError, match="failed validation"):
        load_suite(write(tmp_path, text))


def test_duplicate_rule_names_are_rejected(tmp_path):
    text = VALID.replace("name: status_domain", "name: policy_id_not_null")
    with pytest.raises(ConfigError, match="duplicate rule name"):
        load_suite(write(tmp_path, text))


def test_dataset_needs_at_least_one_rule(tmp_path):
    text = "version: 1\ndatasets:\n  - name: p\n    table: policies\n    rules: []\n"
    with pytest.raises(ConfigError, match="failed validation"):
        load_suite(write(tmp_path, text))


def test_unsupported_version_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="failed validation"):
        load_suite(write(tmp_path, VALID.replace("version: 1", "version: 2")))
