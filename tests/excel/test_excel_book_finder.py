import pytest

from ebf_data.excel.excel_book_finder import find_open_book, get_named_value
from ebf_data.excel.globals import CONSTANTS_WB_NAME
from ebf_data.excel.snapshot.snapshot_table import SNAPSHOT_WB
from ebf_data.excel.cagr.cagr_table import CAGR_WB, CAGR_WKS, ACB


@pytest.mark.integration
class TestWbFinder:

    class TestFindWb:
        def test_can_find_all_wbs(self):
            assert find_open_book(CONSTANTS_WB_NAME) is not None
            assert find_open_book(SNAPSHOT_WB) is not None
            assert find_open_book(CAGR_WB) is not None

    class TestGetNamedValue:
        def test_can_get_named_value(self):
            wb = find_open_book(CAGR_WB)
            sheet = wb.sheets[CAGR_WKS]
            value = get_named_value(sheet, ACB)
            assert value > 0