"""
Unit tests for PriceOrchestrator - verifies wiring only (does it call the
three collaborators correctly and compute the summary right), since each
collaborator already has its own full test suite elsewhere.
"""
from unittest.mock import MagicMock

import pytest

from ebf_data.excel.pricing.pricing_helpers import PriceUpdateResult, SymbolPriceOutcome
from ebf_data.excel.snapshot.option_price_updater import OptionPriceUpdater, OptionType
from ebf_data.excel.snapshot.price_exporter import PriceExporter
from ebf_data.excel.snapshot.price_orchestrator import PriceOrchestrator
from ebf_data.excel.snapshot.price_updater import PriceUpdater


# region helpers
def _option_fetch(**per_type_failed_counts):
    """Build a full four-key option fetch-result; each kwarg (sc/sp/lc/lp)
    gives how many of that type's outcomes are failures (default 0), plus
    one guaranteed success per type."""
    mapping = {
        "sc": OptionType.SHORT_CALL,
        "sp": OptionType.SHORT_PUT,
        "lc": OptionType.LONG_CALL,
        "lp": OptionType.LONG_PUT,
    }
    results = {}
    for key, ot in mapping.items():
        failed_count = per_type_failed_counts.get(key, 0)
        outcomes = [SymbolPriceOutcome(f"{key}-{i}", None, False) for i in range(failed_count)]
        outcomes.append(SymbolPriceOutcome(f"{key}-ok", 1.0, True))
        result = PriceUpdateResult(
            total_symbols=len(outcomes),
            failed=[o.symbol for o in outcomes if not o.success],
        )
        results[ot] = (result, outcomes)
    return results


# endregion

class TestPriceOrchestrator:

    # region fixtures
    @pytest.fixture
    def snapshot(self):
        return MagicMock()

    @pytest.fixture
    def price_updater(self):
        return MagicMock(spec=PriceUpdater)

    @pytest.fixture
    def option_updater(self):
        return MagicMock(spec=OptionPriceUpdater)

    @pytest.fixture
    def exporter(self):
        return MagicMock(spec=PriceExporter)

    @pytest.fixture
    def sut(self, snapshot, price_updater, option_updater, exporter):
        return PriceOrchestrator(
            snapshot, price_updater=price_updater, option_updater=option_updater, exporter=exporter)
    # endregion

    class TestWiring:
        def test_all_collaborators_are_called_and_results_are_exported(self, sut, price_updater, option_updater,
                                                                       exporter):
            equity_fetch = (PriceUpdateResult(total_symbols=1), [SymbolPriceOutcome("AAPL", 200.0, True)])
            option_fetch = _option_fetch()

            price_updater.fetch_prices.return_value = equity_fetch
            option_updater.fetch_all_option_prices.return_value = option_fetch
            exporter.export.return_value = "/fake/path/snapshot.json"

            summary = sut.run()

            price_updater.fetch_prices.assert_called_once_with()
            option_updater.fetch_all_option_prices.assert_called_once_with()
            exporter.export.assert_called_once_with(equity_fetch, option_fetch)
            assert summary.export_path == "/fake/path/snapshot.json"

        def test_default_collaborators_are_wired_to_the_given_snapshot(self, snapshot):
            # No collaborators injected - real ones get built. Safe to
            # instantiate without touching Excel, since none of these
            # constructors access the workbook eagerly.
            orchestrator = PriceOrchestrator(snapshot)

            assert isinstance(orchestrator._price_updater, PriceUpdater)
            assert isinstance(orchestrator._option_updater, OptionPriceUpdater)
            assert isinstance(orchestrator._exporter, PriceExporter)
            assert orchestrator._price_updater._snapshot is snapshot
            assert orchestrator._option_updater._snapshot is snapshot
            assert orchestrator._exporter._snapshot is snapshot

    class TestSummary:
        def test_counts_are_aggregated_across_all_option_types(self, sut, price_updater, option_updater, exporter):
            price_updater.fetch_prices.return_value = (
                PriceUpdateResult(total_symbols=3, failed=["ZZZZ"]), []
            )
            option_updater.fetch_all_option_prices.return_value = _option_fetch(sc=1, lp=2)
            exporter.export.return_value = "irrelevant"

            summary = sut.run()

            assert summary.equity_total == 3
            assert summary.equity_failed == 1
            assert summary.option_total == (1 + 1) + (0 + 1) + (0 + 1) + (2 + 1)  # sc, sp, lc, lp
            assert summary.option_failed == 1 + 0 + 0 + 2

        def test_had_any_failures_are_true_when_failures(self, sut, price_updater, option_updater, exporter):
            price_updater.fetch_prices.return_value = (PriceUpdateResult(), [])
            option_updater.fetch_all_option_prices.return_value = _option_fetch(sp=1)
            exporter.export.return_value = "irrelevant"

            summary = sut.run()

            assert summary.had_any_failures is True

        def test_had_any_failures_false_when_everything_succeeded(self, sut, price_updater, option_updater, exporter):
            price_updater.fetch_prices.return_value = (PriceUpdateResult(total_symbols=1), [])
            option_updater.fetch_all_option_prices.return_value = _option_fetch()
            exporter.export.return_value = "irrelevant"

            summary = sut.run()

            assert summary.had_any_failures is False
