import pytest

from ebf_data.excel.snapshot.snapshot_table import SnapshotTable


class TestSnapshotTable:
    @pytest.fixture
    def sut(self) -> SnapshotTable:
        return SnapshotTable()

    class TestReadStructure:
        def test_size(self, sut: SnapshotTable):
            assert len(sut.df) > 450
            assert len(sut.df.columns) == 205

        def test_headers_are_correct(self, sut: SnapshotTable):
            headers = sut.df.columns.tolist()
            assert "Symbol" in headers
            assert "SC DTE" in headers
            assert "SC Intrinsic Value" in headers
            assert "GUID Lookup" in headers

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
