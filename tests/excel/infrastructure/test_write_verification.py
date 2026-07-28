import pandas as pd
import numpy as np

import pytest
from xlwings import Sheet

from ebf_data.excel.infrastructure.write_verification import PriceWriteVerificationError, verify_column_write, \
    find_verification_sample
from tests.excel.infrastructure.fixtures.xl_base_tester import TesterTable


class TestWriteVerification:
    @pytest.fixture(scope="module")
    def sut(self) -> TesterTable:
        table = TesterTable()
        yield table
        table.close()

    @pytest.fixture
    def sheet(self, sut: TesterTable) -> Sheet:
        return sut.sheet

    class TestFailuresRaise:
        def test_when_cell_is_none(self, sheet: Sheet):
            sheet.range("E5").value = None
            with pytest.raises(PriceWriteVerificationError, match="got None"):
                verify_column_write(sheet, 5, 5, 99.9)

        def test_when_outside_tolerance(self, sheet: Sheet):
            sheet.range("F6").value = 10.002
            with pytest.raises(PriceWriteVerificationError, match="got 10.002"):
                verify_column_write(sheet, 6, 6, 10.0, tolerance=0.001)

        def test_when_non_numeric(self, sheet: Sheet):
            sheet.range("G7").value = "hello"
            with pytest.raises(PriceWriteVerificationError, match="could not compare"):
                verify_column_write(sheet, 7, 7, 1.23)

    class TestSuccessfulWritesDoNotRaise:
        def test_exact_numeric_match(self, sheet: Sheet):
            sheet.range("H8").value = 42.0
            verify_column_write(sheet, 8, 8, 42.0)

        def test_within_tolerance(self, sheet: Sheet):
            sheet.range((5, 3)).value = 10.0004
            verify_column_write(sheet, 5, 3, 10.0, tolerance=0.001)

        def test_both_none(self, sheet: Sheet):
            sheet.range("I9").value = None
            verify_column_write(sheet, 9, 9, None)

class TestFindVerificationSample:
    @pytest.fixture
    def df_index(self):
        return pd.Index([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])

    class TestWhenFetchedPricesExist:
        def test_returns_first_valued_symbol(self, df_index):
            symbol_to_indices = {"AAA": [0],"BBB": [3],"CCC": [7],}
            prices = {"AAA": None,"BBB": 123.45,"CCC": 999.0,}

            FIRST_ROW=2
            result = find_verification_sample(symbol_to_indices, prices, df_index, first_row=FIRST_ROW)

            exp_price = 123.45 # BBB is the first valued symbol
            exp_row = FIRST_ROW + 3 # 3 is BBB's relative row, so we get 5 absolute
            assert result == (exp_row, exp_price)

        def test_uses_the_first_index_in_list_if_symbol_has_multiple_indices(self, df_index):
            symbol_to_indices = {"XYZ": [5, 8, 9],}
            prices = {"XYZ": 77.0}

            FIRST_ROW=10
            exp_row = FIRST_ROW + 5 # 5 is the row at index zero, so row 15 absolute
            result = find_verification_sample(symbol_to_indices, prices, df_index, first_row=FIRST_ROW)
            assert result == (15, 77.0)

        def test_works_with_numpy_int64_index(self):
            """get_loc sometimes returns np.int64 – make sure we handle it."""
            idx = pd.Index(np.arange(5, dtype="int64"))
            symbol_to_indices = {"SYM": [2]}
            prices = {"SYM": 42.0}

            result = find_verification_sample(symbol_to_indices, prices, idx)
            assert result == (2, 42.0)
            assert isinstance(result[0], int)
