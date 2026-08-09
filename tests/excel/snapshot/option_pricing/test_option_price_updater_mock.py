from unittest.mock import MagicMock

import pandas as pd
import pytest
from ebf_domain.money.money import Money
from ebf_trading.domain.value_objects.quotes.quote import Quote

from ebf_data.excel.snapshot.option_price_updater import OptionPriceUpdater, OptionType, get_outcomes
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


class TestOptionPriceUpdaterMock:

    # region fixtures
    @pytest.fixture
    def snapshot_tbl(self):
        snap = MagicMock(spec=SnapshotTable)
        snap.SC_SYMBOL_COLUMN = "SC Symbol"
        snap.SP_SYMBOL_COLUMN = "SP Symbol"
        snap.LC_SYMBOL_COLUMN = "LC Symbol"
        snap.LP_SYMBOL_COLUMN = "LP Symbol"
        return snap

    @pytest.fixture
    def fetcher(self):
        return MagicMock()

    @pytest.fixture
    def sut(self, snapshot_tbl, fetcher):
        return OptionPriceUpdater(snapshot=snapshot_tbl, fetcher=fetcher)
    # endregion

    class TestFetchAllOptionPrices:

        def test_can_update_all_options_in_a_single_call(self, sut, snapshot_tbl, fetcher):
            """One fetch_quotes call should serve every option type."""
            SC = "AAPL260918C00200000"
            SP = "AAPL260918P00180000"
            LC = "MSFT260918C00400000"
            LP = "MSFT260918P00350000"

            snapshot_tbl.df = make_df([
                {"SC Symbol": SC, "SP Symbol": None, "LC Symbol": None, "LP Symbol": None},
                {"SC Symbol": None, "SP Symbol": SP, "LC Symbol": None, "LP Symbol": None},
                {"SC Symbol": None, "SP Symbol": None, "LC Symbol": LC, "LP Symbol": None},
                {"SC Symbol": None, "SP Symbol": None, "LC Symbol": None, "LP Symbol": LP},
            ])
            snapshot_tbl.refresh = MagicMock()

            fetcher.fetch_quotes.return_value = {
                SC: make_quote(SC, bid=1.10, ask=1.25),
                SP: make_quote(SP, bid=0.80, ask=0.95),
                LC: make_quote(LC, bid=2.40, ask=2.60),
                LP: make_quote(LP, bid=1.70, ask=1.85),
            }

            results = sut.fetch_all_option_prices()

            # Only one network call
            fetcher.fetch_quotes.assert_called_once()
            called = set(fetcher.fetch_quotes.call_args[0][0])
            assert called == {SC, SP, LC, LP}

            # Shorts use ask (see quotes above)
            assert get_outcomes(results,OptionType.SHORT_CALL)[0].price == 1.25
            assert get_outcomes(results,OptionType.SHORT_PUT)[0].price == 0.95

            # Longs use bid (see quotes above)
            assert get_outcomes(results,OptionType.LONG_CALL)[0].price == 2.40
            assert get_outcomes(results,OptionType.LONG_PUT)[0].price == 1.70

        def test_empty_workbook_returns_empty_results(self, sut, snapshot_tbl, fetcher):
            snapshot_tbl.df = make_df([], columns=["SC Symbol", "SP Symbol", "LC Symbol", "LP Symbol"])
            snapshot_tbl.refresh = MagicMock()

            results = sut.fetch_all_option_prices()

            for t in (OptionType.SHORT_CALL,OptionType.SHORT_PUT, OptionType.LONG_CALL, OptionType.LONG_PUT):
                result, outcomes = results[t]
                assert result.total_symbols == 0
                assert outcomes == []

            fetcher.fetch_quotes.assert_not_called()

    class TestWhenNoActiveRows:

        def test_when_dataframe_is_empty(self, sut, snapshot_tbl):
            snapshot_tbl.df = make_df([], columns=["SC Symbol"])
            snapshot_tbl.refresh = MagicMock()

            result, outcomes = sut.fetch_short_call_prices()

            assert result.total_symbols == 0
            assert outcomes == []
            sut._fetcher.fetch_quotes.assert_not_called()

        def test_when_no_symbols(self, sut, snapshot_tbl):
            snapshot_tbl.df = make_df([
                {"SC Symbol": None},
                {"SC Symbol": ""},
            ])
            snapshot_tbl.refresh = MagicMock()

            result, outcomes = sut.fetch_short_call_prices()

            assert result.total_symbols == 0
            assert outcomes == []

    class TestShortCallsUsesAsk:

        def test_when_no_failures(self, sut, snapshot_tbl, fetcher):
            occ = "AAPL260918C00200000"
            snapshot_tbl.df = make_df([
                {"SC Symbol": occ},
                {"SC Symbol": occ},  # duplicate row
            ])
            snapshot_tbl.refresh = MagicMock()

            quote = make_quote(occ, bid=1.20, ask=1.45)
            fetcher.fetch_quotes.return_value = {occ: quote}

            result, outcomes = sut.fetch_short_call_prices()

            fetcher.fetch_quotes.assert_called_once_with([occ])
            assert result.total_symbols == 1
            assert result.failed == []
            assert len(outcomes) == 2
            assert all(o.price == 1.45 and o.success for o in outcomes)

        def test_when_failure(self, sut, snapshot_tbl, fetcher):
            occ = "AAPL260918C00200000"
            snapshot_tbl.df = make_df([{"SC Symbol": occ}])
            snapshot_tbl.refresh = MagicMock()
            fetcher.fetch_quotes.return_value = {occ: None}

            result, outcomes = sut.fetch_short_call_prices()

            assert result.failed == [occ]
            assert outcomes[0].success is False
            assert outcomes[0].price is None

    class TestLongCallsUsesBid:

        def test_when_no_failures(self, sut, snapshot_tbl, fetcher):
            occ = "AAPL260918C00200000"
            snapshot_tbl.df = make_df([{"LC Symbol": occ}])
            snapshot_tbl.refresh = MagicMock()

            quote = make_quote(occ, bid=1.20, ask=1.45)
            fetcher.fetch_quotes.return_value = {occ: quote}

            result, outcomes = sut.fetch_long_call_prices()

            fetcher.fetch_quotes.assert_called_once_with([occ])
            assert outcomes[0].price == 1.20  # bid, not ask
            assert outcomes[0].success is True

    class TestLongPutsUsesBid:

        def test_when_no_failures(self, sut, snapshot_tbl, fetcher):
            occ = "AAPL260918P00180000"
            snapshot_tbl.df = make_df([{"LP Symbol": occ}])
            snapshot_tbl.refresh = MagicMock()

            quote = make_quote(occ, bid=0.85, ask=0.95)
            fetcher.fetch_quotes.return_value = {occ: quote}

            result, outcomes = sut.fetch_long_put_prices()

            assert outcomes[0].price == 0.85

    class TestUnparseableSymbolsAreSkipped:

        def test_bad_occ_is_ignored(self, sut, snapshot_tbl, fetcher):
            snapshot_tbl.df = make_df([
                {"SC Symbol": "NOT-AN-OCC"},
                {"SC Symbol": "AAPL260918C00200000"},
            ])
            snapshot_tbl.refresh = MagicMock()

            good_occ = "AAPL260918C00200000"
            quote = make_quote(good_occ, bid=1.0, ask=1.1)
            fetcher.fetch_quotes.return_value = {good_occ: quote}

            result, outcomes = sut.fetch_short_call_prices()

            # Only the valid symbol was sent to the fetcher
            fetcher.fetch_quotes.assert_called_once_with([good_occ])
            assert result.total_symbols == 1
            assert len(outcomes) == 1
            assert outcomes[0].symbol == good_occ

    class TestWithMultipleDistinctSymbols:

        def test_all_symbols_are_requested(self, sut, snapshot_tbl, fetcher):
            occ1 = "AAPL260918C00200000"
            occ2 = "MSFT260918C00400000"
            snapshot_tbl.df = make_df([
                {"SC Symbol": occ1},
                {"SC Symbol": occ2},
            ])
            snapshot_tbl.refresh = MagicMock()

            fetcher.fetch_quotes.return_value = {
                occ1: make_quote(occ1, 1.0, 1.1),
                occ2: make_quote(occ2, 2.0, 2.2),
            }

            result, outcomes = sut.fetch_short_call_prices()

            # Order of the list doesn’t matter
            called_with = fetcher.fetch_quotes.call_args[0][0]
            assert set(called_with) == {occ1, occ2}
            assert result.total_symbols == 2
            assert len(outcomes) == 2
