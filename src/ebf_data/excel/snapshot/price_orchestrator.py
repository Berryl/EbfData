import logging
from dataclasses import dataclass
from pathlib import Path

from ebf_data.excel.pricing.pricing_helpers import PriceUpdateResult, SymbolPriceOutcome
from ebf_data.excel.snapshot.price_exporter import PriceExporter
from ebf_data.excel.snapshot.option_price_updater import OptionPriceUpdater, OptionType
from ebf_data.excel.snapshot.price_updater import PriceUpdater
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

logger = logging.getLogger(__name__)

EquityFetch = tuple[PriceUpdateResult, list[SymbolPriceOutcome]]
OptionFetch = dict[OptionType, tuple[PriceUpdateResult, list[SymbolPriceOutcome]]]

_EMPTY_EQUITY_FETCH: EquityFetch = (PriceUpdateResult(), [])


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
    Runs a fetch-and-export cycle against a snapshot table - full
    (run()), equity-only, or options-only (optionally scoped to a
    subset of OptionType).

    Production usage is PriceOrchestrator(SnapshotTable()).run() - the
    three collaborators default to their real implementations, all wired
    to the same snapshot. Tests inject fakes/mocks for all three, exactly
    like every other class in this pipeline.

    PriceExporter.export() requires all four OptionType keys and an
    equity tuple to be present regardless of which of these methods was
    called - the equity-only and options-only paths pad whatever wasn't
    actually fetched with empty placeholders (matching the already-exercised
    "long_puts: prices: []" shape), so every JSON this class writes has the same
    five-section structure VBA already knows how to read, whether this particular
    run touched all of them or not. Each method also tells PriceExporter which
    sections it actually attempted (vs. padded) - a padded section and a
    genuinely-empty attempted section produce identical price/summary data, and
    only the attempted flag lets VBA tell "nothing to fetch" apart from "wasn't
    fetched" - the distinction that matters for its per-column tooltip, which
    should never overwrite a real result from an earlier pass with a false
    "0 symbols" from a later pass that never touched that section.
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
        """Full run: equity plus all four option types."""
        logger.info("Starting pricing run (equity + all options)")
        equity_fetch = self._price_updater.fetch_prices()
        option_fetch = self._option_updater.fetch_all_option_prices()
        return self._export_and_summarize(
            equity_fetch, option_fetch, equity_attempted=True, attempted_option_types=None)

    def run_equity_only(self) -> PricingRunSummary:
        """
        Equity only. The JSON's four option sections come back present
        but empty AND marked attempted=False - VBA applies 0/0 for each
        and leaves their tooltips untouched, rather than overwriting
        whatever a prior run (e.g. this same Test sequence's options
        stage) correctly wrote there.
        """
        logger.info("Starting pricing run (equity only)")
        equity_fetch = self._price_updater.fetch_prices()
        return self._export_and_summarize(
            equity_fetch, {}, equity_attempted=True, attempted_option_types=set())

    def run_options_only(self, types: set[OptionType] | None = None) -> PricingRunSummary:
        """
        Options only (all four by default, or a subset). The JSON's
        equity section comes back present but empty AND marked
        attempted=False - the same reasoning as run_equity_only()'s option
        sections, just mirrored onto equity.
        """
        logger.info(f"Starting pricing run (options only, types={types or 'all'})")
        option_fetch = self._option_updater.fetch_all_option_prices(types)
        return self._export_and_summarize(
            _EMPTY_EQUITY_FETCH, option_fetch, equity_attempted=False, attempted_option_types=types)

    def _export_and_summarize(
            self,
            equity_fetch: EquityFetch,
            option_fetch: OptionFetch,
            equity_attempted: bool,
            attempted_option_types: set[OptionType] | None,
    ) -> PricingRunSummary:
        option_fetch = self._pad_missing_option_types(option_fetch)
        export_path = self._exporter.export(
            equity_fetch, option_fetch,
            equity_attempted=equity_attempted, attempted_option_types=attempted_option_types)

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

    @staticmethod
    def _pad_missing_option_types(option_fetch: OptionFetch) -> OptionFetch:
        """PriceExporter.export() requires all four OptionType keys -
        fill in empty placeholders for any type this particular run
        didn't actually fetch (a no-op when all four are already there,
        e.g., after an unscoped fetch_all_option_prices())."""
        return {ot: option_fetch.get(ot, (PriceUpdateResult(), [])) for ot in OptionType}