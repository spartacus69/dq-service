# dq-service

Data quality rules that live in YAML instead of in code, compiled to SQL and pushed down to the warehouse.

```yaml
- name: premium_not_negative
  type: range
  column: premium_chf
  min: 0
```

```console
$ dq run -c examples/policies.yml -d examples/warehouse.duckdb
8 checks · 4 passed · 4 failed · 0 warnings (7 ms)
  [FAIL] policies.policy_id_not_null (not_null) — 1/8 rows
  [FAIL] policies.policy_id_unique (unique) — 2/7 rows
  [FAIL] policies.status_in_domain (accepted_values) — 1/8 rows
  [FAIL] policies.premium_not_negative (range) — 1/8 rows
```

Passing checks are hidden unless you ask for `--verbose`: a report you have to scroll through is a report nobody reads.

## The problem

Most data quality checks are written twice: once as a `WHERE` clause in an ETL job, and once, months later, as an incident. They are scattered across pipelines, invisible to the people who consume the data, and impossible to audit as a set.

Treating them as **configuration** changes that. A rule file is a readable contract for one data product: it states what downstream consumers may assume, it is reviewed like code, and it is enforced automatically. Adding a rule is a pull request, not a deployment.

That idea is not new — it is what the data-mesh literature calls *computable governance*, and what dbt tests and Great Expectations implement at a larger scale. This project is a deliberately small, readable core of it.

## How it works

Every rule compiles to one query returning exactly two numbers:

```sql
SELECT COUNT(*) AS total_rows,
       COALESCE(SUM(CASE WHEN "policy_id" IS NULL THEN 1 ELSE 0 END), 0) AS failed_rows
FROM "policies"
```

That uniform shape is the whole design. It means the engine contains no per-rule branching, a rule declared in YAML behaves exactly like one written by hand, and the data never leaves the warehouse — only two integers come back.

```
config.py   YAML -> validated Suite (pydantic, unknown fields rejected)
rules.py    Rule -> SQL           the only place that knows about check semantics
engine.py   Suite -> SuiteResult  runs everything, survives a broken rule
adapters/   the port to a warehouse; DuckDB today, BigQuery next
reporting.py  SuiteResult -> text or JSON
cli.py      argument parsing and exit codes
```

Adding a warehouse means writing one adapter class. Adding a rule type means writing one model with a `to_sql` method. Neither touches the other.

## Rule types

| Type | Level | Checks |
|--------------------|-------|--------------------------------------------------|
| `not_null` | row | the column is populated |
| `unique` | row | the column combination identifies at most one row |
| `accepted_values` | row | the value is in a known domain |
| `range` | row | the number stays within bounds |
| `expression` | row | an arbitrary boolean SQL expression holds |
| `row_count` | table | the table has a plausible size |
| `freshness` | table | the newest timestamp is recent enough |

Every rule accepts `severity` (`error` or `warn`) and `threshold` — the tolerated share of failing rows. A threshold is how you adopt a rule on data that is not clean yet: set it to today's failure rate, then ratchet it down. Rules that pass by accident teach nobody anything.

## Design decisions worth arguing about

**Uniqueness ignores NULL keys.** SQL treats NULLs as distinct, so counting them as duplicates would be misleading. Catch them with a separate `not_null` rule — one defect, one rule, one message.

**An empty table is stale, not fresh.** `MAX(loaded_at)` over zero rows is NULL, and a naive comparison passes. The freshness check treats "no rows at all" as the most severe form of staleness, because a load that silently produced nothing is exactly the failure you most want to hear about.

**A broken rule does not abort the run.** One malformed expression would otherwise hide the state of every rule behind it. Failures to *evaluate* are recorded as data and reported like any other violation.

**Warnings do not fail the build.** Severity separates "stop the pipeline" from "someone should look at this". Use `--fail-on warn` when you disagree.

**`expression` inlines SQL verbatim.** Rule files are trusted input at the same level as application code. Review them like a pull request; never accept one from an untrusted source. The alternative — a parsed mini-language — buys safety that this threat model does not need, at a cost in expressiveness that it cannot afford.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python examples/seed.py                                   # 8 rows, 4 deliberately broken
dq run -c examples/policies.yml -d examples/warehouse.duckdb
dq run -c examples/policies.yml -d examples/warehouse.duckdb --format json
dq validate -c examples/policies.yml                      # schema check, no database needed
```

Exit codes, because a scheduler reads them:

| Code | Meaning |
|------|--------------------------------------------------------|
| 0 | everything passed, or only warnings were raised |
| 1 | at least one rule failed at the configured severity |
| 2 | the run could not start — bad config, unreachable database |

## Development

```bash
ruff check src tests examples
ruff format src tests examples
mypy                     # strict
pytest --cov --cov-report=term-missing
```

CI runs all four on Python 3.10 through 3.13. 55 tests, 95% branch coverage — the uncovered lines are connection-failure paths that need a broken filesystem to reach.

Tests run against a real in-memory DuckDB rather than a mocked cursor. Mocking here would only prove that string concatenation works; the bugs that actually occur are NULL-handling and dialect bugs, and only a real engine surfaces those.

## Roadmap

- BigQuery adapter — the reason the adapter port exists
- Emit results as OpenMetrics so failures become alerts, not log lines
- Column-level profiling to propose an initial rule set from existing data
- Per-rule row samples for the failing rows, behind a flag

## License

MIT
