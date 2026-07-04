from unittest.mock import MagicMock, ANY

import pandas as pd
from ebf_trading.domain.entities.transaction_events.transaction_event_type import TransactionEventType

from ebf_data.excel.orchestrators.opex_processor import OpexProcessor


def make_opex_processor(cagr_mock: MagicMock) -> OpexProcessor:
    """
    _close_trade_in_cagr only touches self._cagr, so we bypass __init__
    entirely - no real CagrTable/SnapshotTable, no find_open_book, no real
    Excel touched.
    """
    sut = OpexProcessor.__new__(OpexProcessor)
    sut._cagr = cagr_mock
    return sut


def make_match(strike: float = 115.0) -> pd.DataFrame:
    return pd.DataFrame({
        "Symbol": ["FCX"],
        "ID": [20],
        "Strike Price": [strike],
    }, index=[42])


def make_snapshot_row(last_price: float, sc_exp_date="2026-06-19") -> pd.Series:
    return pd.Series({
        "Symbol": "FCX_20",
        "Last Price": last_price,
        "SC Exp Date": sc_exp_date,
    })


class TestCloseTradeInCagr:

    def test_delegates_to_close_trade_leg_with_underlying_price_from_last_price(self):
        cagr_mock = MagicMock()
        sut = make_opex_processor(cagr_mock)
        match = make_match()
        row = make_snapshot_row(last_price=15.30)

        sut._close_trade_in_cagr(match, row, TransactionEventType.EXPIRATION)

        cagr_mock.close_trade_leg.assert_called_once_with(
            match, TransactionEventType.EXPIRATION, 15.30, ANY
        )

    def test_passes_through_assignment_event(self):
        """_close_trade_in_cagr doesn't hardcode the event - it must pass
        through whatever the caller determined (EXPIRATION today,
        ASSIGNMENT once that path exists)."""
        cagr_mock = MagicMock()
        sut = make_opex_processor(cagr_mock)
        match = make_match()
        row = make_snapshot_row(last_price=5.45)

        sut._close_trade_in_cagr(match, row, TransactionEventType.ASSIGNMENT)

        cagr_mock.close_trade_leg.assert_called_once_with(
            match, TransactionEventType.ASSIGNMENT, 5.45, ANY
        )

    def test_exit_fill_time_is_market_close_on_sc_exp_date(self):
        """exit_fill_time must be market close (4 PM ET) on the SC Exp Date
        from the snapshot row - not a dummy string, not None."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        cagr_mock = MagicMock()
        sut = make_opex_processor(cagr_mock)
        match = make_match()
        row = make_snapshot_row(last_price=15.30, sc_exp_date="2026-06-19")

        sut._close_trade_in_cagr(match, row, TransactionEventType.EXPIRATION)

        _, kwargs = cagr_mock.close_trade_leg.call_args
        args = cagr_mock.close_trade_leg.call_args[0]
        exit_fill_time = args[3]

        assert isinstance(exit_fill_time, datetime)
        assert exit_fill_time.hour == 16
        assert exit_fill_time.minute == 0
        assert exit_fill_time.tzinfo == ZoneInfo("America/New_York")

    def test_does_not_mutate_the_match_dataframe(self):
        """Confirms the match row is passed through as-is, not copied,
        modified, or stripped of columns before reaching close_trade_leg."""
        cagr_mock = MagicMock()
        sut = make_opex_processor(cagr_mock)
        match = make_match(strike=120.0)
        row = make_snapshot_row(last_price=10.10)

        sut._close_trade_in_cagr(match, row, TransactionEventType.EXPIRATION)

        passed_match = cagr_mock.close_trade_leg.call_args[0][0]
        assert passed_match is match
        assert passed_match.loc[42, "Strike Price"] == 120.0