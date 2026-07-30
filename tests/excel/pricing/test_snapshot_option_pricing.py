import logging

import pytest

from ebf_data.excel.snapshot.option_price_updater import OptionPriceUpdater
from ebf_data.excel.snapshot.price_updater import PriceUpdateResult
from tests.excel.pricing.pricing_scenarios import SnapshotScenario_ShortCalls, SnapshotScenario_ShortPuts


class TestSnapshotShortCallPricing:
    SC_EXP_DATE_COLUMN = "SC Exp Date"

    @pytest.fixture(scope="module")
    def source(self) -> SnapshotScenario_ShortCalls:
        table = SnapshotScenario_ShortCalls()
        yield table
        table.close()

    @pytest.fixture(scope="class")
    def sut(self, source) -> tuple[PriceUpdateResult, OptionPriceUpdater]:
        opu = OptionPriceUpdater(source)
        result: PriceUpdateResult = opu.update_short_call_prices()
        source.refresh()

        return result, opu

    def test_all_active_rows_have_a_price(self, source, sut: tuple[PriceUpdateResult, OptionPriceUpdater]):
        _, opu = sut
        df = source.df
        active = df[df[self.SC_EXP_DATE_COLUMN].notna() & (df[self.SC_EXP_DATE_COLUMN].isin(df.index) != "")]
        assert not active.empty, f"No active rows found in scenario workbook '{source.book.name}'"

        for idx, row in active.iterrows():
            price = row[opu.SC_ASK_COLUMN]
            symbol = row[opu.SP_SYMBOL_COLUMN]
            assert price is not None, f"{symbol}: SC Ask is None after update"
            assert float(price) > 0, f"{symbol}: SC Ask {price} is not positive"

class TestSnapshotShortPutPricing:
    SP_EXP_DATE_COLUMN = "SP Exp Date"

    @pytest.fixture(scope="module")
    def source(self) -> SnapshotScenario_ShortPuts:
        table = SnapshotScenario_ShortPuts()
        yield table
        table.close()

    @pytest.fixture(scope="class")
    def sut(self, source) -> tuple[PriceUpdateResult, OptionPriceUpdater]:
        opu = OptionPriceUpdater(source)
        result: PriceUpdateResult = opu.update_short_put_prices()
        source.refresh()

        return result, opu

    def test_all_active_rows_have_a_price(self, source, sut: tuple[PriceUpdateResult, OptionPriceUpdater]):
        _, opu = sut
        df = source.df
        active = df[df[self.SP_EXP_DATE_COLUMN].notna() & (df[self.SP_EXP_DATE_COLUMN].isin(df.index) != "")]
        assert not active.empty, f"No active rows found in scenario workbook '{source.book.name}'"

        for idx, row in active.iterrows():
            price = row[opu.SP_ASK_COLUMN]
            symbol = row[opu.SP_SYMBOL_COLUMN]
            assert price is not None, f"{symbol}: {opu.SP_ASK_COLUMN} is None after update"
            assert float(price) > 0, f"{symbol}: {opu.SP_ASK_COLUMN} {price} is not positive"

    # @pytest.mark.skip(reason="run on demand only")
    class TestShortCallRunWithLogging:
        def test_can_run_with_logging(self, caplog):
            sut = SnapshotScenario_ShortCalls()
            with caplog.at_level(logging.DEBUG):
                OptionPriceUpdater(sut).update_short_call_prices()
            if caplog.text.strip():
                print("\n----- OptionPriceUpdater log output -----")
                print(caplog.text)
                print("----- end log -----\n")

            sut.refresh()
