"""Command-line interface for the dq data-quality service.

Exit codes are part of the CLI contract for automation and CI systems:

===  ==========================================================
0    every rule passed, or only warnings were raised
1    at least one rule failed at the configured severity
2    the run could not start (bad config, unreachable database)
===  ==========================================================
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from dq import __version__
from dq.adapters.duckdb import DuckDBAdapter
from dq.config import load_suite
from dq.engine import run_suite
from dq.errors import DQError
from dq.reporting import format_json, format_text

EXIT_OK = 0
EXIT_FAILED_CHECKS = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dq",
        description="Run metadata-driven data quality checks against a warehouse table.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="log every rule")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="evaluate a rule suite")
    run.add_argument("-c", "--config", type=Path, required=True, help="YAML rule suite")
    run.add_argument(
        "-d", "--database", default=":memory:", help="DuckDB file (default: in-memory)"
    )
    run.add_argument("--format", choices=("text", "json"), default="text")
    run.add_argument(
        "--fail-on",
        choices=("error", "warn", "never"),
        default="error",
        help="which severity turns into a non-zero exit code",
    )

    validate = sub.add_parser("validate", help="check a rule suite without touching data")
    validate.add_argument("-c", "--config", type=Path, required=True)

    return parser


def _configure_logging(*, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(verbose=args.verbose)

    try:
        suite = load_suite(args.config)

        if args.command == "validate":
            print(
                f"{args.config}: valid — {len(suite.datasets)} dataset(s), "
                f"{suite.rule_count} rule(s)"
            )
            return EXIT_OK

        with DuckDBAdapter(args.database, read_only=False) as adapter:
            result = run_suite(suite, adapter)
    except DQError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.format == "json":
        print(format_json(result))
    else:
        print(format_text(result, verbose=args.verbose))

    if args.fail_on == "never":
        return EXIT_OK
    if args.fail_on == "warn" and result.failed:
        return EXIT_FAILED_CHECKS
    return EXIT_OK if result.ok else EXIT_FAILED_CHECKS


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
