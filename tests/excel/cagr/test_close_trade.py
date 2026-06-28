from unittest.mock import MagicMock

import pandas as pd
import pytest
from ebf_core.guards.guards import ContractError
from ebf_trading.domain.entities.transaction_events.transaction_event_type import TransactionEventType

from ebf_data.excel.cagr.cagr_table import CagrTable


def make_cagr_table(df: pd.DataFrame) -> CagrTable:
    """
    Build a CagrTable backed by a real pandas DataFrame, with the Excel
    boundary (book/sheet/table) fully mocked. No real Excel/COM is touched -
    table.update is a MagicMock we can inspect, never a live workbook.
    """
    cagr = CagrTable.__new__(CagrTable)  # bypass __init__ -> bypass find_open_book
    cagr.book = MagicMock()
    cagr.sheet = MagicMock()
    cagr.table = MagicMock()
    cagr.name = "CagrTable"
    cagr._df = df
    return cagr


def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Symbol": ["UUUU", "UUUU", "FCX"],
        "ID": [2, 2, 20],
        "Position": ["SC", "SC", "SC"],
        "Is Closed": ["", "", ""],
        "Exit Trigger": ["", "", ""],
        "Exit Und Price": [None, None, None],
        "Exit Trade": ["", "", ""],
        "Exp Date": ["2026-06-19", "2026-06-19", "2026-06-19"],
        "Strike Price": [16.50, 18.00, 5.00],
        "Entry Trade": [
            "STO 20 Jun-26 $16.50 C @ 0.22",
            "STO 20 Jun-26 $18.00 C @ 0.31",
            "STO 5 Jun-26 $5.00 C @ 0.10",
        ],
    }, index=[10, 11, 12])  # deliberately non-contiguous, non-zero-based index


class TestUpdateRow:

    def test_updates_only_the_targeted_row(self):
        cagr = make_cagr_table(sample_df())

        cagr.update_row(11, {"Is Closed": "Y", "Exit Trigger": "OPEX"})

        assert cagr._df.loc[11, "Is Closed"] == "Y"
        assert cagr._df.loc[11, "Exit Trigger"] == "OPEX"
        # sibling rows with the same Symbol/ID must be untouched
        assert cagr._df.loc[10, "Is Closed"] == ""
        assert cagr._df.loc[12, "Is Closed"] == ""

    def test_pushes_full_table_back_through_excel(self):
        cagr = make_cagr_table(sample_df())

        cagr.update_row(10, {"Is Closed": "Y"})

        cagr.table.update.assert_called_once()
        pushed_df = cagr.table.update.call_args[0][0]
        assert pushed_df.loc[10, "Is Closed"] == "Y"

    def test_raises_on_unknown_index_label(self):
        cagr = make_cagr_table(sample_df())

        with pytest.raises(KeyError, match="999"):
            cagr.update_row(999, {"Is Closed": "Y"})

    def test_raises_on_unknown_column(self):
        cagr = make_cagr_table(sample_df())

        with pytest.raises(KeyError, match="Not A Real Column"):
            cagr.update_row(10, {"Not A Real Column": "Y"})

    def test_does_not_mutate_excel_on_failed_validation(self):
        cagr = make_cagr_table(sample_df())

        with pytest.raises(KeyError):
            cagr.update_row(999, {"Is Closed": "Y"})

        cagr.table.update.assert_not_called()


class TestCloseTrade:

    def test_closes_exactly_the_matched_row_among_duplicates(self):
        """
        This is the essential case: two open SC legs share the same
        Symbol/ID (UUUU, 2). Only the caller's matching logic (not
        Symbol/ID) can say which one is being closed. close_trade must
        write to that exact row and leave the other untouched.
        """
        cagr = make_cagr_table(sample_df())
        matched = cagr._df.loc[[11]]  # the $18.00 strike leg, specifically

        cagr.close_trade(matched, TransactionEventType.EXPIRATION, underlying_price=15.30)

        assert cagr._df.loc[11, "Is Closed"] == "Y"
        assert cagr._df.loc[11, "Exit Trigger"] == "OPEX"
        assert cagr._df.loc[11, "Exit Trade"] == "Expiration"
        assert cagr._df.loc[11, "Exit Und Price"] == 15.30

        # the other open leg for the same Symbol/ID must remain untouched
        assert cagr._df.loc[10, "Is Closed"] == ""
        assert cagr._df.loc[10, "Exit Trade"] == ""

    def test_writes_assignment_event_value(self):
        cagr = make_cagr_table(sample_df())
        matched = cagr._df.loc[[12]]

        cagr.close_trade(matched, TransactionEventType.ASSIGNMENT, underlying_price=5.45)

        assert cagr._df.loc[12, "Exit Trade"] == "Assignment"

    def test_writes_exercise_event_value(self):
        cagr = make_cagr_table(sample_df())
        matched = cagr._df.loc[[12]]

        cagr.close_trade(matched, TransactionEventType.EXERCISE, underlying_price=5.45)

        assert cagr._df.loc[12, "Exit Trade"] == "Exercise"

    def test_does_not_set_exit_fill_time(self):
        """Exit Fill Time depends on OpexCalendar, not wired in yet - confirm
        close_trade doesn't invent a placeholder value for it."""
        cagr = make_cagr_table(sample_df())
        matched = cagr._df.loc[[10]]

        cagr.close_trade(matched, TransactionEventType.EXPIRATION, underlying_price=15.30)

        pushed_df = cagr.table.update.call_args[0][0]
        assert "Exit Fill Time" not in pushed_df.columns or pushed_df.loc[10, "Exit Fill Time"] != "OPEX"

    def test_raises_on_empty_match(self):
        cagr = make_cagr_table(sample_df())
        empty = cagr._df.iloc[0:0]

        msg = r"closing trade row must contain exactly one row, got 0"
        with pytest.raises(ContractError, match=msg):
            cagr.close_trade(empty, TransactionEventType.EXPIRATION, underlying_price=15.30)

    def test_raises_on_multiple_rows_passed(self):
        """close_trade refuses to guess if the caller hands it more than
        one candidate - disambiguation is the caller's job, not ours."""
        cagr = make_cagr_table(sample_df())
        both_uuuu = cagr._df.loc[[10, 11]]

        msg = r"closing trade row must contain exactly one row, got 2"
        with pytest.raises(ContractError, match=msg):
            cagr.close_trade(both_uuuu, TransactionEventType.EXPIRATION, underlying_price=15.30)