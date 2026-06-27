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
