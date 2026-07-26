"""
Tests for PriceUpdater against the SnapshotScenarioTable.

TestRealPriceUpdate: hits real YFinance - proves the full pipeline
end to end against a real workbook. Slow by nature; requires network.

TestMockedPriceUpdate: mocks _fetch_prices to test write mechanics
in isolation, without network dependency. (placeholder for now)
"""
import pytest

from ebf_data.excel.snapshot.option_price_updater import OptionPriceUpdater
from ebf_data.excel.snapshot.price_updater import PriceUpdateResult
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
        opu = OptionPriceUpdater(source)
        result: PriceUpdateResult = opu.update_short_call_prices()
        source.refresh()

        return source, result

    def test_all_active_rows_have_a_price(self, sut):
        wb, _ = sut
        df = wb.df
        active = df[df["SC Exp Date"].notna() & (df["SC Exp Date"] != "")]
        assert not active.empty, f"No active rows found in scenario workbook {wb.book.name}"

        for idx, row in active.iterrows():
            price = row["SC Current Ask"]
            symbol = row["SC Symbol"]
            assert price is not None, f"{symbol}: SC Ask is None after update"
            assert float(price) > 0, f"{symbol}: SC Ask {price} is not positive"
