import re

import pandas as pd
import pytest
from ebf_core.guards.guards import ContractError

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

        @pytest.mark.parametrize("symbol", ["  "])
        def test_symbol_must_be_valued(self, symbol: str, sut: CagrTable):
            msg = re.escape("Arg 'symbol' cannot be an empty string")
            with pytest.raises(ContractError, match=msg):
                sut.get_trade(symbol, 1)

        def test_symbol_must_exist(self, sut: CagrTable):
            msg = re.escape("No trades found for symbol '---' with ID=1")
            with pytest.raises(ContractError, match=msg):
                sut.get_trade("---", 1)

        def test_id_must_positive_if_not_none(self, sut: CagrTable):
            msg = re.escape("Arg 'id_val' must be positive")
            with pytest.raises(ContractError, match=msg):
                sut.get_trade("UUUU", 0)

        class TestQueries:

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

            def test_multiple_filters(self, uuuu2: pd.DataFrame, sut: CagrTable):
                results = sut.by_position(uuuu2, "SC")
                results = sut.closed_legs(results)

                assert len(results) == 8

            def test_chaining_filters(self, uuuu2: pd.DataFrame, sut: CagrTable):
                results = sut.by_position(uuuu2, "SC").pipe(sut.where_closed)
                assert len(results) == 8

    class TestMaxId:

        @pytest.mark.parametrize("symbol, expected", [("UUUU", 3), ("AMZN", 25), ("FCX", 20), ])
        def test_max_id_for_symbol_parametrized(self, sut: CagrTable, symbol: str, expected: int):
            assert sut.max_id_for_symbol(symbol) >= expected
