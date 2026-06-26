import xlwings as xw

from ebf_data.excel.excel_book_finder import find_open_book
from ebf_data.excel.globals import CAGR_WB, CAGR_WKS, CAGR_TABLE


class CagrReader:
    def __init__(self) -> None:
        self.wb = find_open_book(CAGR_WB)
        self.sheet: xw.Sheet = self.wb.sheets[CAGR_WKS]
        self.table_name = CAGR_TABLE

    def read_table_values(self) -> list[list]:
        table = self.sheet.tables[self.table_name]
        return table.range.options(ndim=2).value
