"""Shared fixtures.

The seed table deliberately contains one of each defect the rules look for, so
a test that expects a clean table is testing the wrong thing.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from dq.adapters.duckdb import DuckDBAdapter

SEED_SQL = """
CREATE TABLE policies (
    policy_id     VARCHAR,
    customer_id   VARCHAR,
    status        VARCHAR,
    premium_chf   DOUBLE,
    valid_from    TIMESTAMP,
    loaded_at     TIMESTAMP
);

INSERT INTO policies VALUES
    ('P-001', 'C-100', 'active',    1200.00, TIMESTAMP '2026-01-01 00:00:00', CURRENT_TIMESTAMP),
    ('P-002', 'C-101', 'active',     840.50, TIMESTAMP '2026-02-01 00:00:00', CURRENT_TIMESTAMP),
    ('P-003', 'C-102', 'cancelled',    0.00, TIMESTAMP '2026-02-15 00:00:00', CURRENT_TIMESTAMP),
    ('P-004', 'C-103', 'pending',    310.00, TIMESTAMP '2026-03-01 00:00:00', CURRENT_TIMESTAMP),
    -- defect: duplicated business key
    ('P-004', 'C-104', 'active',     455.00, TIMESTAMP '2026-03-02 00:00:00', CURRENT_TIMESTAMP),
    -- defect: NULL in a mandatory column
    (NULL,    'C-105', 'active',     999.00, TIMESTAMP '2026-03-03 00:00:00', CURRENT_TIMESTAMP),
    -- defect: status outside the known domain
    ('P-006', 'C-106', 'unknown',    120.00, TIMESTAMP '2026-03-04 00:00:00', CURRENT_TIMESTAMP),
    -- defect: negative premium
    ('P-007', 'C-107', 'active',    -50.00,  TIMESTAMP '2026-03-05 00:00:00', CURRENT_TIMESTAMP);
"""

ROW_COUNT = 8


@pytest.fixture
def adapter() -> Iterator[DuckDBAdapter]:
    """An in-memory DuckDB pre-loaded with the seed table."""
    with DuckDBAdapter(":memory:") as adapter:
        adapter.execute(SEED_SQL)
        yield adapter


@pytest.fixture
def empty_adapter() -> Iterator[DuckDBAdapter]:
    """Same schema, no rows — the case most checks get wrong."""
    with DuckDBAdapter(":memory:") as adapter:
        adapter.execute(SEED_SQL.split("INSERT INTO")[0])
        yield adapter
