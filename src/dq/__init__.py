"""Metadata-driven data quality checks for analytical tables.

Quality rules live in YAML, not in code. The engine compiles each rule into
SQL that is pushed down to the warehouse, so the data never leaves it.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
