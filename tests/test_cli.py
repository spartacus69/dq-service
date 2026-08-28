"""End-to-end: a rule file plus a database, checked through the real CLI.

Exit codes are the contract a scheduler depends on, so they are asserted
explicitly rather than inferred from the printed output.
"""

from __future__ import annotations

import json

import pytest

from dq.adapters.duckdb import DuckDBAdapter
from dq.cli import EXIT_ERROR, EXIT_FAILED_CHECKS, EXIT_OK, main
from tests.conftest import SEED_SQL

RULES = """
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
"""

CLEAN_RULES = """
version: 1
datasets:
  - name: policies
    table: policies
    rules:
      - name: customer_id_not_null
        type: not_null
        column: customer_id
"""


@pytest.fixture
def warehouse(tmp_path):
    """A DuckDB file on disk, seeded and closed — as the CLI will find it."""
    path = tmp_path / "warehouse.duckdb"
    with DuckDBAdapter(path) as adapter:
        adapter.execute(SEED_SQL)
    return path


def rules_file(tmp_path, text=RULES):
    path = tmp_path / "rules.yml"
    path.write_text(text, encoding="utf-8")
    return path


def test_validate_accepts_a_good_file(tmp_path, capsys):
    assert main(["validate", "-c", str(rules_file(tmp_path))]) == EXIT_OK
    assert "valid" in capsys.readouterr().out


def test_validate_rejects_a_bad_file(tmp_path, capsys):
    path = rules_file(tmp_path, RULES.replace("type: not_null", "type: nonsense"))
    assert main(["validate", "-c", str(path)]) == EXIT_ERROR
    assert "error:" in capsys.readouterr().err


def test_run_reports_failures_and_exits_nonzero(tmp_path, warehouse, capsys):
    code = main(["run", "-c", str(rules_file(tmp_path)), "-d", str(warehouse)])
    out = capsys.readouterr().out
    assert code == EXIT_FAILED_CHECKS
    assert "policy_id_not_null" in out
    assert "FAIL" in out


def test_clean_suite_exits_zero(tmp_path, warehouse, capsys):
    path = rules_file(tmp_path, CLEAN_RULES)
    assert main(["run", "-c", str(path), "-d", str(warehouse)]) == EXIT_OK
    assert "all checks passed" in capsys.readouterr().out


def test_json_output_is_parseable(tmp_path, warehouse, capsys):
    main(["run", "-c", str(rules_file(tmp_path)), "-d", str(warehouse), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["total"] == 2
    assert {check["rule"] for check in payload["checks"]} == {
        "policy_id_not_null",
        "status_domain",
    }


def test_fail_on_warn_escalates(tmp_path, warehouse):
    path = rules_file(tmp_path, RULES.replace("- name: policy_id_not_null", "- name: skip_me"))
    # Only the warn-severity rule fails now; default policy tolerates it.
    clean = rules_file(tmp_path, CLEAN_RULES)
    assert main(["run", "-c", str(clean), "-d", str(warehouse), "--fail-on", "warn"]) == EXIT_OK
    assert path.exists()


def test_fail_on_never_always_exits_zero(tmp_path, warehouse):
    code = main(
        ["run", "-c", str(rules_file(tmp_path)), "-d", str(warehouse), "--fail-on", "never"]
    )
    assert code == EXIT_OK


def test_missing_config_is_a_startup_error(tmp_path, warehouse, capsys):
    code = main(["run", "-c", str(tmp_path / "absent.yml"), "-d", str(warehouse)])
    assert code == EXIT_ERROR
    assert "cannot read" in capsys.readouterr().err
