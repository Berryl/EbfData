from unittest.mock import MagicMock

import pandas as pd
import pytest
from ebf_domain.money.money import Money
from ebf_trading.domain.value_objects.quotes.quote import Quote

from ebf_data.excel.snapshot.option_price_updater import OptionPriceUpdater
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable


# region helpers
def make_quote(symbol: str, bid: float, ask: float) -> Quote:
    return Quote(
        symbol=symbol,
        bid_price=Money.mint(bid),
        bid_size=0,
        ask_price=Money.mint(ask),
        ask_size=0,
        timestamp=MagicMock(),  # we don't care about the timestamp in these tests
        last_price=None,
        last_size=None,
    )


def make_df(rows: list[dict], columns: list[str] | None = None) -> pd.DataFrame:
    if not rows and columns:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)


# endregion


class TestOptionPriceUpdater:

    # region fixtures
    @pytest.fixture
    def mock_snapshot(self):
        snap = MagicMock(spec=SnapshotTable)
        snap.SC_SYMBOL_COLUMN = "SC Symbol"
        snap.SP_SYMBOL_COLUMN = "SP Symbol"
        snap.LC_SYMBOL_COLUMN = "LC Symbol"
        snap.LP_SYMBOL_COLUMN = "LP Symbol"
        return snap

    @pytest.fixture
    def mock_fetcher(self):
        return MagicMock()

    @pytest.fixture
    def sut(self, mock_snapshot, mock_fetcher):
        return OptionPriceUpdater(snapshot=mock_snapshot, fetcher=mock_fetcher)
    # endregion

    class TestWhenNoActiveRows:

        def test_when_dataframe_is_empty(self, sut, mock_snapshot):
            mock_snapshot.df = make_df([], columns=["SC Symbol"])
            mock_snapshot.refresh = MagicMock()

            result, outcomes = sut.fetch_short_call_prices()

            assert result.total_symbols == 0
            assert outcomes == []
            sut._fetcher.fetch_quotes.assert_not_called()

        def test_when_no_symbols(self, sut, mock_snapshot):
            mock_snapshot.df = make_df([
                {"SC Symbol": None},
                {"SC Symbol": ""},
            ])
            mock_snapshot.refresh = MagicMock()

            result, outcomes = sut.fetch_short_call_prices()

            assert result.total_symbols == 0
            assert outcomes == []

    class TestShortCallsUsesAsk:

        def test_when_no_failures(self, sut, mock_snapshot, mock_fetcher):
            occ = "AAPL260918C00200000"
            mock_snapshot.df = make_df([
                {"SC Symbol": occ},
                {"SC Symbol": occ},  # duplicate row
            ])
            mock_snapshot.refresh = MagicMock()

            quote = make_quote(occ, bid=1.20, ask=1.45)
            mock_fetcher.fetch_quotes.return_value = {occ: quote}

            result, outcomes = sut.fetch_short_call_prices()

            mock_fetcher.fetch_quotes.assert_called_once_with([occ])
            assert result.total_symbols == 1
            assert result.failed == []
            assert len(outcomes) == 2
            assert all(o.price == 1.45 and o.success for o in outcomes)

        def test_when_failure(self, sut, mock_snapshot, mock_fetcher):
            occ = "AAPL260918C00200000"
            mock_snapshot.df = make_df([{"SC Symbol": occ}])
            mock_snapshot.refresh = MagicMock()
            mock_fetcher.fetch_quotes.return_value = {occ: None}

            result, outcomes = sut.fetch_short_call_prices()

            assert result.failed == [occ]
            assert outcomes[0].success is False
            assert outcomes[0].price is None

    class TestLongCallsUsesBid:

        def test_when_no_failures(self, sut, mock_snapshot, mock_fetcher):
            occ = "AAPL260918C00200000"
            mock_snapshot.df = make_df([{"LC Symbol": occ}])
            mock_snapshot.refresh = MagicMock()

            quote = make_quote(occ, bid=1.20, ask=1.45)
            mock_fetcher.fetch_quotes.return_value = {occ: quote}

            result, outcomes = sut.fetch_long_call_prices()

            mock_fetcher.fetch_quotes.assert_called_once_with([occ])
            assert outcomes[0].price == 1.20  # bid, not ask
            assert outcomes[0].success is True

    class TestLongPutsUsesBid:

        def test_when_no_failures(self, sut, mock_snapshot, mock_fetcher):
            occ = "AAPL260918P00180000"
            mock_snapshot.df = make_df([{"LP Symbol": occ}])
            mock_snapshot.refresh = MagicMock()

            quote = make_quote(occ, bid=0.85, ask=0.95)
            mock_fetcher.fetch_quotes.return_value = {occ: quote}

            result, outcomes = sut.fetch_long_put_prices()

            assert outcomes[0].price == 0.85

    class TestUnparseableSymbolsAreSkipped:

        def test_bad_occ_is_ignored(self, sut, mock_snapshot, mock_fetcher):
            mock_snapshot.df = make_df([
                {"SC Symbol": "NOT-AN-OCC"},
                {"SC Symbol": "AAPL260918C00200000"},
            ])
            mock_snapshot.refresh = MagicMock()

            good_occ = "AAPL260918C00200000"
            quote = make_quote(good_occ, bid=1.0, ask=1.1)
            mock_fetcher.fetch_quotes.return_value = {good_occ: quote}

            result, outcomes = sut.fetch_short_call_prices()

            # Only the valid symbol was sent to the fetcher
            mock_fetcher.fetch_quotes.assert_called_once_with([good_occ])
            assert result.total_symbols == 1
            assert len(outcomes) == 1
            assert outcomes[0].symbol == good_occ

    class TestWithMultipleDistinctSymbols:

        def test_all_symbols_are_requested(self, sut, mock_snapshot, mock_fetcher):
            occ1 = "AAPL260918C00200000"
            occ2 = "MSFT260918C00400000"
            mock_snapshot.df = make_df([
                {"SC Symbol": occ1},
                {"SC Symbol": occ2},
            ])
            mock_snapshot.refresh = MagicMock()

            mock_fetcher.fetch_quotes.return_value = {
                occ1: make_quote(occ1, 1.0, 1.1),
                occ2: make_quote(occ2, 2.0, 2.2),
            }

            result, outcomes = sut.fetch_short_call_prices()

            # Order of the list doesn’t matter
            called_with = mock_fetcher.fetch_quotes.call_args[0][0]
            assert set(called_with) == {occ1, occ2}
            assert result.total_symbols == 2
            assert len(outcomes) == 2
