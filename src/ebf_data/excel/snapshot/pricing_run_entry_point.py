"""
Standalone entry point for a full pricing run.

Invoked by VBA via PowerShell as a separate OS process.
This script attaches read-only to the already-open production
workbook via find_open_book, fetches, writes JSON to runtime/pricing/pending/, and exits.
VBA owns polling of that folder and doing the actual updates into the workbook.

Exit code 0: a JSON file was written. Individual symbol failures do NOT
    affect this - they're recorded in the JSON's own summary sections,
    and VBA's job is to skip them, not treat the run as failed.
Exit code 1: the run failed before any JSON could be written (Excel not
    open, workbook not found, etc.). Nothing landed in pending/, so VBA
    should not proceed to read it.
"""
import logging
import sys

from ebf_data.excel.snapshot.price_orchestrator import PriceOrchestrator
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        summary = PriceOrchestrator(SnapshotTable()).run()
    except Exception:
        logger.exception("Pricing run failed before a JSON file could be written")
        return 1

    logger.info(f"Done. Wrote {summary.export_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())