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
        """Return all expired short calls. Returns an empty DataFrame if none."""
        return self._get_expired_short_calls(was_assigned=False)

    def get_assigned_short_calls(self) -> pd.DataFrame:
        """Return all assigned short calls. Returns an empty DataFrame if none."""
        return self._get_expired_short_calls(was_assigned=True)

    def _get_expired_short_calls(self, was_assigned: bool = False) -> pd.DataFrame:
        """Internal helper for expired vs assigned short calls."""
        df = self.df

        conditions = {
            False: (df["SC Intrinsic Value"] == 0),  # expired
            True: (df["SC Intrinsic Value"] > 0)  # assigned
        }

        expired = df[
            (df["SC DTE"] <= 0) & conditions[was_assigned]
            ]

        return expired