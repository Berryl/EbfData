import logging

import pytest

from ebf_data.excel.snapshot.snapshot_table import SnapshotTable
from ebf_data.excel.snapshot.price_updater import PriceUpdater
from ebf_data.excel.snapshot.option_price_updater import OptionPriceUpdater


class TestSnapshotTable:
    @pytest.fixture
    def sut(self) -> SnapshotTable:
        return SnapshotTable()

    class TestReadStructure:
        def test_size(self, sut: SnapshotTable):
            assert len(sut.df) > 400
            assert len(sut.df.columns) > 200

        def test_headers_are_correct(self, sut: SnapshotTable):
            headers = sut.df.columns.tolist()
            assert "Symbol" in headers
            assert "SC DTE" in headers
            assert "SC Intrinsic Value" in headers
            assert "GUID Lookup" in headers

    @pytest.mark.skip(reason="stale test, needs to be updated")
    class TestExpiredShortCalls:

        def test_get_expired_short_calls(self, sut: SnapshotTable):
            expired = sut.get_expired_short_calls()

            actual_symbols = expired['Symbol'].tolist()

            expected_symbols = ["FCX_20", "MARA_4.1", "MARA_4.2", "MARA_4.3", "SPCX", "TSLA"]

            for symbol in expected_symbols:
                assert symbol in actual_symbols, f"Missing symbol: {symbol}"

        def test_get_assigned_short_calls(self, sut: SnapshotTable):
            assigned = sut.get_assigned_short_calls()

            assert assigned.empty

    @pytest.mark.skip(reason="run on demand only")
    class TestPricing:
        def test_can_get_pricing(self, sut: SnapshotTable):
            PriceUpdater(sut).fetch_prices()

    @pytest.mark.skip(reason="run on demand only")
    class TestEquityRunWithLogging:
        def test_can_run_with_logging(self, sut: SnapshotTable, caplog):
            with caplog.at_level(logging.DEBUG):
                PriceUpdater(sut).fetch_prices()
            if caplog.text.strip():
                print("\n----- PriceUpdater log output -----")
                print(caplog.text)
                print("----- end log -----\n")

            sut.refresh()

    class TestOptionPricing:
        @pytest.fixture
        def opu(self, sut) -> OptionPriceUpdater:
            return OptionPriceUpdater(sut)

        @pytest.mark.skip(reason="run on demand only")
        def test_can_get_short_call_pricing(self, opu):
            opu.update_short_call_prices()

        @pytest.mark.skip(reason="run on demand only")
        def test_can_get_short_put_pricing(self, opu):
            opu.update_short_put_prices()
