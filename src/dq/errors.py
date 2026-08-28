"""Exception hierarchy.

A single base class lets callers catch everything this package raises without
catching unrelated failures.
"""

from __future__ import annotations


class DQError(Exception):
    """Base class for all errors raised by this package."""


class ConfigError(DQError):
    """The rule suite could not be read or failed validation."""


class AdapterError(DQError):
    """The warehouse rejected a query or returned an unexpected shape."""
