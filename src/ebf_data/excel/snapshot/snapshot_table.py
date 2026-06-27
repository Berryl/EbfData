import pandas as pd

from ebf_data.excel.excel_book_finder import find_open_book
from ebf_data.xlTableBase import xlTable

SNAPSHOT_WB = "snapshot.xlsm"
SNAPSHOT_WKS = "SNAP"
SNAPSHOT_TABLE = "SnapshotTable"


class SnapshotTable(xlTable):
    def __init__(self) -> None:
        super().__init__(find_open_book(SNAPSHOT_WB), SNAPSHOT_WKS, SNAPSHOT_TABLE)

    def get_expired_short_calls(self) -> pd.DataFrame:
        pass
