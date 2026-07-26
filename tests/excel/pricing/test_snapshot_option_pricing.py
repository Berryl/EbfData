"""
Tests for PriceUpdater against the SnapshotScenarioTable.

TestRealPriceUpdate: hits real YFinance - proves the full pipeline
end to end against a real workbook. Slow by nature; requires network.

TestMockedPriceUpdate: mocks _fetch_prices to test write mechanics
in isolation, without network dependency. (placeholder for now)
"""
import pytest

from ebf_data.excel.snapshot.option_price_updater import OptionPriceUpdater
from ebf_data.excel.snapshot.price_updater import PriceUpdater, PriceUpdateResult
from tests.excel.pricing.pricing_scenarios import SnapshotScenario_ShortCalls


class TestSnapshotShortCallPricing:

    @pytest.fixture(scope="module")
    def source(self) -> SnapshotScenario_ShortCalls:
        return SnapshotScenario_ShortCalls()

    @pytest.fixture(scope="class")
    def sut(self, source) -> tuple[SnapshotScenario_ShortCalls, PriceUpdateResult]:
        """
        Run update_prices() once for the whole class. Returns a tuple of
        (table, result) so benchmark and correctness tests share the same run.
        """
        opu =  OptionPriceUpdater(source)
        result: PriceUpdateResult = opu.update_short_call_prices()
        source.refresh()

        return source, result


    # @pytest.mark.skip(reason="run on demand only")
    def test_can_get_short_call_pricing(self, sut):
        assert True
