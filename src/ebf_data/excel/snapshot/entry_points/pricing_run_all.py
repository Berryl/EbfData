"""
Standalone entry point for a full pricing run.

Exit code 0: a JSON file was written.
Exit code 1: the run failed before any JSON could be written.
Exit code 2: argparse usage error (e.g. --workbook missing entirely).

Notes
Invoked by VBA via PowerShell as a separate OS process.
This script attaches read-only to an already-open workbook via
find_open_book, fetches, writes JSON to runtime/pricing/pending/, and
exits. VBA owns polling of that folder and doing the actual updates
into the workbook.

--workbook is required, not defaulted - deliberately, so a
misconfigured or missing caller fails loudly rather than silently
falling back to production (the whole reason this parameter exists in
the first place: there was previously no way to target anything except
the hardcoded production workbook at all, which left no safe way to
test a real end-to-end run without touching production directly).

Exit code 0: Individual symbol failures do NOT affect this - they're
    recorded in the JSON's own summary sections, and VBA's job is to
    skip them, not treat the run as failed.
Exit code 1: Excel may not be open, the workbook not found, etc., or nothing landed in pending/, so VBA
    should not proceed to read it.
"""
import argparse
import logging
import sys

from ebf_data.excel.snapshot.price_orchestrator import PriceOrchestrator
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a full pricing fetch-and-export cycle.")
    parser.add_argument("--workbook",  required=True,
                        help="Exact filename of the already-open workbook to price, e.g. snapshot.xlsm.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger.info(f"Target workbook: {args.workbook}")

    try:
        summary = PriceOrchestrator(SnapshotTable(args.workbook)).run()
    except Exception: # noqa intentioally broad exception
        logger.exception("Pricing run failed before a JSON file could be written")
        return 1

    logger.info(f"Done. Wrote {summary.export_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())