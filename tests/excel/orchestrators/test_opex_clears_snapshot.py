from unittest.mock import MagicMock

import pandas as pd

from ebf_data.excel.orchestrators.opex_processor import OpexProcessor
from ebf_data.excel.orchestrators.symbol_translator import SymbolTranslator


def make_open_sc_candidate(id_val: int) -> pd.DataFrame:
    return pd.DataFrame({
        "Symbol": ["FCX"],
        "ID": [id_val],
        "Position": ["SC"],
        "Is Closed": [""],
    })


def make_opex_processor(cagr_mock: MagicMock, snapshot_mock: MagicMock) -> OpexProcessor:
    """
    Bypasses __init__ (which would call find_open_book) but still wires a
    real SymbolTranslator against the mocked CagrTable, since
    SymbolTranslator is cheap, real, and already independently tested.
    No real Excel is touched anywhere in this test.
    """
    sut = OpexProcessor.__new__(OpexProcessor)
    sut._cagr = cagr_mock
    sut._snapshot = snapshot_mock
    sut._symbol_translator = SymbolTranslator(cagr_mock)
    return sut


class TestCloseOutExpiredShortCallsClearsSnapshot:

    def test_clears_snapshot_row_after_successful_close(self):
        to_close = pd.DataFrame({
            "Symbol": ["FCX_20"],
            "Last Price": [15.30],
            "SC Exp Date": ["2026-06-19"],
        }, index=[99])  # deliberately non-trivial index

        snapshot_mock = MagicMock()
        snapshot_mock.get_expired_short_calls.return_value = to_close

        cagr_mock = MagicMock()
        cagr_mock.get_trade.return_value = make_open_sc_candidate(id_val=20)
        cagr_mock.by_position.return_value = make_open_sc_candidate(id_val=20)
        cagr_mock.where_open.return_value = make_open_sc_candidate(id_val=20)

        sut = make_opex_processor(cagr_mock, snapshot_mock)

        sut.close_out_expired_short_calls()

        cagr_mock.close_trade_leg.assert_called_once()
        snapshot_mock.clear_short_call_columns.assert_called_once_with(99)

    def test_does_not_clear_snapshot_when_no_open_candidates(self):
        """If there's no open SC in CAGR at all, nothing was closed -
        snapshot must not be cleared."""
        to_close = pd.DataFrame({
            "Symbol": ["FCX_20"],
            "Last Price": [15.30],
        }, index=[99])

        snapshot_mock = MagicMock()
        snapshot_mock.get_expired_short_calls.return_value = to_close

        empty = pd.DataFrame(columns=["Symbol", "ID", "Position", "Is Closed"])
        cagr_mock = MagicMock()
        cagr_mock.get_trade.return_value = empty
        cagr_mock.by_position.return_value = empty
        cagr_mock.where_open.return_value = empty

        sut = make_opex_processor(cagr_mock, snapshot_mock)

        sut.close_out_expired_short_calls()

        cagr_mock.close_trade_leg.assert_not_called()
        snapshot_mock.clear_short_call_columns.assert_not_called()

    def test_does_not_clear_snapshot_when_no_id_match_found(self):
        """Open SC candidates exist for the symbol, but none match the
        translated ID - close_trade_leg never runs, so snapshot must stay
        untouched for that row."""
        to_close = pd.DataFrame({
            "Symbol": ["FCX_20"],
            "Last Price": [15.30],
        }, index=[99])

        snapshot_mock = MagicMock()
        snapshot_mock.get_expired_short_calls.return_value = to_close

        wrong_id_candidate = make_open_sc_candidate(id_val=999)  # not 20
        cagr_mock = MagicMock()
        cagr_mock.get_trade.return_value = wrong_id_candidate
        cagr_mock.by_position.return_value = wrong_id_candidate
        cagr_mock.where_open.return_value = wrong_id_candidate

        sut = make_opex_processor(cagr_mock, snapshot_mock)

        sut.close_out_expired_short_calls()

        cagr_mock.close_trade_leg.assert_not_called()
        snapshot_mock.clear_short_call_columns.assert_not_called()

    def test_continues_to_next_row_after_a_skip_and_still_clears_the_good_one(self):
        """Two rows: the first has no open SC (skipped), the second succeeds. The
        skip must not prevent the second row from being processed and
        cleared, and only the second row's index should be cleared."""
        to_close = pd.DataFrame({
            "Symbol": ["CLOSED_1", "FCX_20"],
            "Last Price": [1.00, 15.30],
            "SC Exp Date": ["2026-06-19", "2026-06-19"],
        }, index=[50, 99])

        snapshot_mock = MagicMock()
        snapshot_mock.get_expired_short_calls.return_value = to_close

        empty = pd.DataFrame(columns=["Symbol", "ID", "Position", "Is Closed"])
        good_candidate = make_open_sc_candidate(id_val=20)

        cagr_mock = MagicMock()
        # first row (CLOSED_1) -> no open SC; second row (FCX_20) -> matches
        cagr_mock.get_trade.side_effect = [empty, good_candidate]
        cagr_mock.by_position.side_effect = [empty, good_candidate]
        cagr_mock.where_open.side_effect = [empty, good_candidate]

        sut = make_opex_processor(cagr_mock, snapshot_mock)

        sut.close_out_expired_short_calls()

        cagr_mock.close_trade_leg.assert_called_once()
        snapshot_mock.clear_short_call_columns.assert_called_once_with(99)
