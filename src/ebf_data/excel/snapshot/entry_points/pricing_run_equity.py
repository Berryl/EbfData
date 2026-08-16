"""
Standalone entry point for an equity-only pricing run.

Same invocation model as pricing_run_entry_point.py (VBA -> PowerShell
-> this, as a separate OS process, attaching read-only via
find_open_book) - just scoped to equity, leaving the JSON's four option
sections present but empty. See PriceOrchestrator.run_equity_only()
docstring for why that's a safe shape for VBA to apply.

Exit codes match pricing_run_entry_point.py: 0 = JSON written
(regardless of individual symbol failures), 1 = failed before any JSON
could be written, 2 = argparse usage error (e.g. --workbook missing).
"""
import argparse
import logging
import sys

from ebf_data.excel.snapshot.price_orchestrator import PriceOrchestrator
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an equity-only pricing fetch-and-export cycle.")
    parser.add_argument(
        "--workbook",
        required=True,
        help="Exact filename of the already-open workbook to price, e.g. snapshot.xlsm.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger.info(f"Target workbook: {args.workbook}")

    try:
        summary = PriceOrchestrator(SnapshotTable(args.workbook)).run_equity_only()
    except Exception: # noqa intentioally broad exception
        logger.exception("Equity-only pricing run failed before a JSON file could be written")
        return 1

    logger.info(f"Done. Wrote {summary.export_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())