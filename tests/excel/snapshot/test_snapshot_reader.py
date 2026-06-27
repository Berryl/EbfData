import pytest

from ebf_data.excel.snapshot.snapshot_reader import SnapshotReader


class TestSnapshotReader:
    @pytest.fixture
    def sut(self) -> SnapshotReader:
        return SnapshotReader()

    class TestReadTableValues:
        def test_can_read_table(self, sut: SnapshotReader):
            values = sut.read_table_values()

            assert values
            assert len(values) > 450
            assert values[0]

    class TestHeaders:
        def test_can_read_headers(self, sut: SnapshotReader):
            headers = sut.read_table_values()[0]
            assert "Symbol" in headers
            assert "SC Exp Date" in headers
            assert "GUID Lookup" in headers

            #
            # def test_can_find_fcx20_rows(self, sut: CagrReader):
            #     values = sut.read_table_values()
            #     headers = values[0]
            #     trade_index = headers.index("Trade ID")
            #
            #     rows = [row for row in values[1:] if row[trade_index] == "FCX20"]
            #
            #     assert len(rows) == 9
            #
            # def test_can_read_fcx20_positions(self, sut: CagrReader):
            #     values = sut.read_table_values()
            #     headers = values[0]
            #     trade_index = headers.index("Trade ID")
            #     position_index = headers.index("Position")
            #
            #     rows = [row for row in values[1:] if row[trade_index] == "FCX20"]
            #     positions = [row[position_index] for row in rows]

            # assert positions == ["LC", "LC", "SC", "LC", "SP", "SC", "SC", "PLUG", "PLUG"]
