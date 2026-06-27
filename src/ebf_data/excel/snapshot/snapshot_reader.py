import xlwings as xw
from mypy.fastparse import Any

from ebf_data.excel.excel_book_finder import find_open_book
from ebf_data.excel.globals import SNAPSHOT_WB, SNAPSHOT_WKS, SNAPSHOT_TABLE


class SnapshotReader:
    def __init__(self) -> None:
        self.wb = find_open_book(SNAPSHOT_WB)
        self.sheet: xw.Sheet = self.wb.sheets[SNAPSHOT_WKS]
        self.table_name = SNAPSHOT_TABLE

    def read_table_values(self) -> list[list[Any]]:
        table = self.sheet.tables[self.table_name]
        return table.range.options(ndim=2).value
