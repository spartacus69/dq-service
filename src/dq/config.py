"""Loading and validating a rule suite from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from dq.errors import ConfigError
from dq.rules import Rule


class Dataset(BaseModel):
    """One table and the rules that apply to it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    table: str = Field(min_length=1, description="Physical table, optionally schema-qualified.")
    rules: list[Rule] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_rule_names(self) -> Dataset:
        seen: set[str] = set()
        for rule in self.rules:
            if rule.name in seen:
                raise ValueError(f"duplicate rule name {rule.name!r} in dataset {self.name!r}")
            seen.add(rule.name)
        return self


class Suite(BaseModel):
    """A whole rule file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    datasets: list[Dataset] = Field(min_length=1)

    @property
    def rule_count(self) -> int:
        return sum(len(dataset.rules) for dataset in self.datasets)


def load_suite(path: Path) -> Suite:
    """Read and validate a YAML rule suite.

    Raises:
        ConfigError: the file is missing, is not valid YAML, or breaks the schema.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read rule file {path}: {exc}") from exc

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a YAML mapping at the top level")

    try:
        return Suite.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{path} failed validation:\n{exc}") from exc


__all__ = ["Dataset", "Suite", "load_suite"]
