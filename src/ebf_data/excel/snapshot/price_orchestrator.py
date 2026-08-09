import logging
from dataclasses import dataclass
from pathlib import Path

from ebf_data.excel.snapshot.price_exporter import PriceExporter
from ebf_data.excel.snapshot.option_price_updater import OptionPriceUpdater
from ebf_data.excel.snapshot.price_updater import PriceUpdater
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PricingRunSummary:
    """High-level counts for logging only (the JSON itself carries the per-symbol detail)"""
    equity_total: int
    equity_failed: int
    option_total: int
    option_failed: int
    export_path: Path

    @property
    def had_any_failures(self) -> bool:
        return self.equity_failed > 0 or self.option_failed > 0


class PriceOrchestrator:
    """
    Runs one full fetch-and-export cycle against a snapshot table.

    Production usage is PriceOrchestrator(SnapshotTable()).run() - the
    three collaborators default to their real implementations, all wired
    to the same snapshot. Tests inject fakes/mocks for all three, exactly
    like every other class in this pipeline.
    """

    def __init__(
            self,
            snapshot: SnapshotTable,
            price_updater: PriceUpdater | None = None,
            option_updater: OptionPriceUpdater | None = None,
            exporter: PriceExporter | None = None,
    ) -> None:
        self._price_updater = price_updater or PriceUpdater(snapshot)
        self._option_updater = option_updater or OptionPriceUpdater(snapshot)
        self._exporter = exporter or PriceExporter(snapshot)

    def run(self) -> PricingRunSummary:
        logger.info("Starting pricing run")

        equity_fetch = self._price_updater.fetch_prices()
        option_fetch = self._option_updater.fetch_all_option_prices()

        export_path = self._exporter.export(equity_fetch, option_fetch)

        equity_result, _ = equity_fetch
        option_total = sum(result.total_symbols for result, _ in option_fetch.values())
        option_failed = sum(len(result.failed) for result, _ in option_fetch.values())

        summary = PricingRunSummary(
            equity_total=equity_result.total_symbols,
            equity_failed=len(equity_result.failed),
            option_total=option_total,
            option_failed=option_failed,
            export_path=export_path,
        )

        level = logging.WARNING if summary.had_any_failures else logging.INFO
        logger.log(
            level,
            f"Pricing run complete: equity {summary.equity_total - summary.equity_failed}/"
            f"{summary.equity_total}, options {option_total - option_failed}/{option_total} "
            f"succeeded, wrote {export_path}",
        )

        return summary