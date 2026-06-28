from unittest.mock import MagicMock

import pandas as pd

from ebf_data.excel.snapshot.snapshot_table import SnapshotTable, CLEARED_SHORT_CALL_COLUMNS


def make_snapshot_table(df: pd.DataFrame) -> SnapshotTable:
    """
    Build a SnapshotTable backed by a real pandas DataFrame, with the Excel
    boundary (book/sheet/table) fully mocked. No real Excel/COM is touched -
    table.update is a MagicMock we can inspect, never a live workbook.
    """
    snap = SnapshotTable.__new__(SnapshotTable)
    snap.book = MagicMock()
    snap.sheet = MagicMock()
    snap.table = MagicMock()
    snap.name = "SnapshotTable"
    snap._df = df
    return snap


def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Symbol": ["FCX_20", "MARA_4.2"],
        "Last Price": [15.30, 8.10],
        "SC Exp Date": ["2026-06-19", "2026-06-19"],
        "SC Strike Price": [115.0, 4.0],
        "SC Qty": [2, 1],
        "SC Book Date": ["2026-01-30", "2026-02-15"],
        "SC Fill Date": ["2026-01-30", "2026-02-15"],
        "SC Book Price": [1.75, 0.50],
        "SC Fill Delta": [0.3, 0.4],
        "SC Current Ask": [0.05, 0.10],
        "SC Current Delta": [0.02, 0.05],
        "SC Buy Back Cutoff": [0.10, 0.15],
        "SC Intrinsic Value": [0, 0],
        "SC DTE": [0, 0],
    }, index=[7, 8])


class TestClearShortCallColumns:

    def test_clears_only_the_documented_columns_for_one_row(self):
        snap = make_snapshot_table(sample_df())

        snap.clear_short_call_columns(7)

        for col in CLEARED_SHORT_CALL_COLUMNS:
            assert pd.isna(snap._df.loc[7, col]), f"{col!r} was not cleared"

    def test_leaves_other_columns_untouched(self):
        snap = make_snapshot_table(sample_df())

        snap.clear_short_call_columns(7)

        assert snap._df.loc[7, "Symbol"] == "FCX_20"
        assert snap._df.loc[7, "Last Price"] == 15.30
        assert snap._df.loc[7, "SC Intrinsic Value"] == 0
        assert snap._df.loc[7, "SC DTE"] == 0

    def test_leaves_other_rows_untouched(self):
        snap = make_snapshot_table(sample_df())

        snap.clear_short_call_columns(7)

        assert snap._df.loc[8, "SC Strike Price"] == 4.0
        assert snap._df.loc[8, "SC Book Price"] == 0.50

    def test_pushes_full_table_back_through_excel(self):
        snap = make_snapshot_table(sample_df())

        snap.clear_short_call_columns(8)

        snap.table.update.assert_called_once()
        pushed_df = snap.table.update.call_args[0][0]
        assert pd.isna(pushed_df.loc[8, "SC Exp Date"])