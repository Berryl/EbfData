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

    class TestGetTrade:

        @pytest.fixture
        def fcx20(self, sut: CagrTable) -> pd.DataFrame:
            return sut.get_trade("FCX", 20)

        def test_can_read_fcx20_details(self, fcx20: pd.DataFrame):
            positions = fcx20['Position'].tolist()

            assert len(positions) >= 9
            assert all(p in ["LC", "SC", "SP", "PLUG"] for p in positions)

            from collections import Counter
            count = Counter(positions)
            assert count["LC"] >= 3
            assert count.get("PLUG", 0) >= 2

            open_sc_count = (
                fcx20
                .query('Position == "SC" and `Is Closed` != `Is Closed`')  # blank = NaN
                .shape[0]
            )
            assert open_sc_count >= 1