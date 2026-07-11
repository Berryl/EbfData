import pytest

from tests.excel.pricing.pricing_tester import SnapshotScenarioTable


class TestSnapshotPricingTable:
    @pytest.fixture
    def sut(self) -> SnapshotScenarioTable:
        return SnapshotScenarioTable()

    class TestReadStructure:
        def test_size(self, sut):
            assert len(sut.df) > 450
            assert len(sut.df.columns) > 200

        def test_headers_are_correct(self, sut):
            headers = sut.df.columns.tolist()
            assert "Symbol" in headers
            assert "SC DTE" in headers
            assert "SC Intrinsic Value" in headers
            assert "GUID Lookup" in headers

    class  TestPriceUpdater:
        def test_updates_last_price(self, sut):
            pass
