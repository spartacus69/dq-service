"""Create a small DuckDB warehouse to demo the checks against.

python examples/seed.py
dq run -c examples/policies.yml -d examples/warehouse.duckdb
"""

from __future__ import annotations

from pathlib import Path

from dq.adapters.duckdb import DuckDBAdapter

TARGET = Path(__file__).parent / "warehouse.duckdb"

SEED_SQL = """
DROP TABLE IF EXISTS policies;

CREATE TABLE policies (
    policy_id     VARCHAR,
    customer_id   VARCHAR,
    status        VARCHAR,
    premium_chf   DOUBLE,
    valid_from    TIMESTAMP,
    loaded_at     TIMESTAMP
);

INSERT INTO policies VALUES
    ('P-001', 'C-100', 'active',    1200.00, TIMESTAMP '2026-01-01', CURRENT_TIMESTAMP),
    ('P-002', 'C-101', 'active',     840.50, TIMESTAMP '2026-02-01', CURRENT_TIMESTAMP),
    ('P-003', 'C-102', 'cancelled',    0.00, TIMESTAMP '2026-02-15', CURRENT_TIMESTAMP),
    ('P-004', 'C-103', 'pending',    310.00, TIMESTAMP '2026-03-01', CURRENT_TIMESTAMP),
    ('P-004', 'C-104', 'active',     455.00, TIMESTAMP '2026-03-02', CURRENT_TIMESTAMP),
    (NULL,    'C-105', 'active',     999.00, TIMESTAMP '2026-03-03', CURRENT_TIMESTAMP),
    ('P-006', 'C-106', 'unknown',    120.00, TIMESTAMP '2026-03-04', CURRENT_TIMESTAMP),
    ('P-007', 'C-107', 'active',     -50.00, TIMESTAMP '2026-03-05', CURRENT_TIMESTAMP);
"""


def main() -> None:
    TARGET.unlink(missing_ok=True)
    with DuckDBAdapter(TARGET) as adapter:
        adapter.execute(SEED_SQL)
    print(f"seeded {TARGET} with 8 rows (4 of them deliberately broken)")


if __name__ == "__main__":
    main()
