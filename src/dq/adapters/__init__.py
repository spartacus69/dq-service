"""Warehouse adapters."""

from dq.adapters.base import Adapter
from dq.adapters.duckdb import DuckDBAdapter

__all__ = ["Adapter", "DuckDBAdapter"]
