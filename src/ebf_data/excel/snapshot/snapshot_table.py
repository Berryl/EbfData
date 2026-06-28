import pandas as pd
from ebf_trading.domain.entities.transaction_events.transaction_event_type import TransactionEventType

from ebf_data.excel.excel_book_finder import find_open_book
from ebf_data.excel.xlTableBase import xlTable

SNAPSHOT_WB = "snapshot.xlsm"
SNAPSHOT_WKS = "SNAP"
SNAPSHOT_TABLE = "SnapshotTable"


CLEARED_SHORT_CALL_COLUMNS = [
    "SC Exp Date",
    "SC Strike Price",
    "SC Qty",
    "SC Book Date",
    "SC Fill Date",
    "SC Book Price",
    "SC Fill Delta",
    "SC Current Ask",
    "SC Current Delta",
    "SC Buy Back Cutoff",
]


class SnapshotTable(xlTable):
    def __init__(self) -> None:
        super().__init__(find_open_book(SNAPSHOT_WB), SNAPSHOT_WKS, SNAPSHOT_TABLE)

    def get_expired_short_calls(self) -> pd.DataFrame:
        """Return all expired short calls. Returns an empty DataFrame if none."""
        return self._get_expired_short_calls(event=TransactionEventType.EXPIRATION)

    def get_assigned_short_calls(self) -> pd.DataFrame:
        """Return all assigned short calls. Returns an empty DataFrame if none."""
        return self._get_expired_short_calls(TransactionEventType.ASSIGNMENT)

    def clear_short_call_columns(self, index_label) -> None:
        """
        Clear short-call-specific columns for one row, after its
        matching CAGR leg has been closed out.
        """
        self.update_row(index_label, {col: None for col in CLEARED_SHORT_CALL_COLUMNS})

    # region helpers
    def _get_expired_short_calls(self, event: TransactionEventType) -> pd.DataFrame:
        df = self.df

        conditions = {
            TransactionEventType.EXPIRATION: (df["SC Intrinsic Value"] == 0),
            TransactionEventType.ASSIGNMENT: (df["SC Intrinsic Value"] > 0)
        }

        expired = df[
            (df["SC DTE"] <= 0) & conditions[event]
            ]

        return expired
    # endregion