import pandas as pd
import pytest

from ebf_data.excel.cagr.cagr_table import CagrTable


class TestCagrReader:
    @pytest.fixture
    def sut(self) -> CagrTable:
        return CagrTable()

    class TestReadStructure:
        def test_size_expectations(self, sut: CagrTable):
            assert len(sut.df) > 6500
            assert len(sut.df.columns) == 100

        def test_headers_are_correct(self, sut: CagrTable):
            headers = sut.df.columns.tolist()
            assert "Symbol" in headers
            assert "ID" in headers
            assert "Position" in headers
            assert "Is Closed" in headers
            assert "GUID Lookup" in headers

    class TestQueries:

        @pytest.fixture
        def uuuu2(self, sut: CagrTable) -> pd.DataFrame:
            # UUUU is fully closed, so we aren't testing a moving target here
            return sut.get_trade("UUUU", 2)

        def test_get_trade_details(self, uuuu2: pd.DataFrame):
            assert len(uuuu2) == 12

            positions = uuuu2['Position'].tolist()

            assert len(positions) >= 12
            assert all(p in ["LC", "LNG", "SC", "SP"] for p in positions)

            from collections import Counter
            count = Counter(positions)
            assert count["LC"] == 1
            assert count["LNG"] == 1
            assert count["SP"] == 2
            assert count["SC"] == 8

        @pytest.mark.parametrize("position, expected_count", [("LC", 1), ("LNG", 1), ("SC", 8), ("SP", 2)])
        def test_by_position(self, uuuu2: pd.DataFrame, sut: CagrTable, position: str, expected_count: int):
            results = sut.by_position(uuuu2, position)
            assert len(results) == expected_count

        def test_is_closed_mask(self, uuuu2: pd.DataFrame, sut: CagrTable):
            mask = sut.is_closed(uuuu2)

            assert len(mask) == len(uuuu2)
            assert mask.all(), "All legs in this campaign are closed"

        def test_is_open_mask(self, uuuu2: pd.DataFrame, sut: CagrTable):
            mask = sut.is_open(uuuu2)

            assert len(mask) == len(uuuu2)
            assert not mask.any(), "No trades should be open in this closed campaign"

        def test_closed_legs(self, uuuu2: pd.DataFrame, sut: CagrTable):
            assert len(sut.closed_legs(uuuu2)) == 12

        def test_open_legs(self, uuuu2: pd.DataFrame, sut: CagrTable):
            assert len(sut.open_legs(uuuu2)) == 0

        def test_is_closed_with_by_position(self, uuuu2: pd.DataFrame, sut: CagrTable):
            sc_trades = sut.by_position(uuuu2, "SC")

            closed_sc_mask = sut.is_closed(sc_trades)

            assert len(closed_sc_mask) == len(sc_trades)
            assert closed_sc_mask.all(), "All SC trades in this campaign should be closed"