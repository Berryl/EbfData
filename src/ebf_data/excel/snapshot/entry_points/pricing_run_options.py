"""
Standalone entry point for an options-only pricing run, optionally
scoped to a subset of option types.

The same invocation model as pricing_run_entry_point.py (VBA -> PowerShell
-> this, as a separate OS process, attaching read-only via
find_open_book) - just scoped to options, leaving the JSON's equity
section present but empty. See PriceOrchestrator.run_options_only()
docstring for why that's a safe shape for VBA to apply.

--option-types: same usage as the OptionPriceUpdater.

Exit codes match pricing_run_entry_point.py, with one addition:
0 = JSON written (regardless of individual symbol failures)
1 = failed before any JSON could be written
2 = argparse usage error, OR an invalid --option-types value
"""
import argparse
import logging
import sys

from ebf_data.excel.snapshot.option_price_updater import OptionType
from ebf_data.excel.snapshot.price_orchestrator import PriceOrchestrator
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an options-only pricing fetch-and-export cycle.")
    parser.add_argument(
        "--workbook",
        required=True,
        help="Exact filename of the already-open workbook to price, e.g. snapshot.xlsm.",
    )
    parser.add_argument(
        "--option-types",
        default=None,
        help=(
            "Comma-separated subset of option types to fetch: "
            "short_call, short_put, long_call, long_put. Omit for all four (default)."
        ),
    )
    return parser.parse_args()


def _parse_option_types(raw: str | None) -> set[OptionType] | None:
    if raw is None:
        return None
    try:
        return {OptionType(name.strip()) for name in raw.split(",") if name.strip()}
    except ValueError as e:
        print(f"Invalid --option-types value: {e}", file=sys.stderr)
        raise SystemExit(2)


def main() -> int:
    args = parse_args()
    option_types = _parse_option_types(args.option_types)
    logger.info(f"Target workbook: {args.workbook}, option types: {option_types or 'all'}")

    try:
        summary = PriceOrchestrator(SnapshotTable(args.workbook)).run_options_only(option_types)
    except Exception: # noqa intentioally broad exception
        logger.exception("Options-only pricing run failed before a JSON file could be written")
        return 1

    logger.info(f"Done. Wrote {summary.export_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())