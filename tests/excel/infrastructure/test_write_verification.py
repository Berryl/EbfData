import pytest
from xlwings import Sheet

from ebf_data.excel.infrastructure.write_verification import PriceWriteVerificationError, verify_column_write
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
