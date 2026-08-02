# tests/test_yfinance_option_fetcher.py
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from ebf_domain.money.money import Money
from ebf_trading.domain.value_objects.option_specific.symbol_conversion import symbol_converter as sc

from ebf_data.excel.pricing.option_price_fetcher import OptionPriceFetcher
from ebf_data.excel.pricing.yfinance_option_fetcher import YFinanceOptionFetcher


# region helper
def make_chain_df(
        contract_symbols: list[str],
        *,
        asks: list[float | None] | None = None,
        bids: list[float | None] | None = None,
        lasts: list[float | None] | None = None,
) -> pd.DataFrame:
    """Minimal DataFrame that mimics yfinance option_chain calls/puts."""
    data: dict = {"contractSymbol": contract_symbols}
    if asks is not None:
        data["ask"] = asks
    if bids is not None:
        data["bid"] = bids
    if lasts is not None:
        data["lastPrice"] = lasts
    return pd.DataFrame(data)


# endregion


@pytest.fixture
def sut() -> OptionPriceFetcher:
    return YFinanceOptionFetcher()


class TestFetchQuotes:
    class TestUnsuccessfulConditions:

        def test_empty_list_returns_empty_dict(self, sut):
            assert sut.fetch_quotes([]) == {}

        def test_unparseable_symbols_become_none(self, sut):
            result = sut.fetch_quotes(["INVALID1", "NOT-AN-OCC", "SPY"])
            assert result == {
                "INVALID1": None,
                "NOT-AN-OCC": None,
                "SPY": None,
            }

        def test_no_matching_contract_returns_none(self, sut):
            occ_target = "AAPL250117C00150000"
            occ_available = "AAPL250117C00200000"

            calls = make_chain_df([occ_available], asks=[5.0], bids=[4.8])
            puts = make_chain_df([], asks=[], bids=[])
            mock_chain = MagicMock(calls=calls, puts=puts)

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                mock_ticker_cls.return_value.option_chain.return_value = mock_chain
                result = sut.fetch_quotes([occ_target])

            assert result == {occ_target: None}

        def test_both_bid_and_ask_missing_returns_none(self, sut):
            occ = "AAPL250117C00150000"
            yf_symbol = sc.to_symbol(sc.to_option(occ))

            calls = make_chain_df([yf_symbol], asks=[None], bids=[None])
            puts = make_chain_df([])
            mock_chain = MagicMock(calls=calls, puts=puts)

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                mock_ticker_cls.return_value.option_chain.return_value = mock_chain
                result = sut.fetch_quotes([occ])

            assert result == {occ: None}

        def test_option_chain_exception_sets_whole_group_to_none(self, sut):
            symbols = ["AAPL250117C00150000", "AAPL250117P00150000"]

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                mock_ticker_cls.return_value.option_chain.side_effect = RuntimeError("Yahoo is down")
                result = sut.fetch_quotes(symbols)

            assert result == {s: None for s in symbols}

    class TestSuccessfulConditions:

        def test_full_quote_both_sides_present(self, sut):
            occ = "AAPL250117C00150000"
            yf_symbol = sc.to_symbol(sc.to_option(occ))

            calls = make_chain_df(
                [yf_symbol],
                asks=[3.45],
                bids=[3.20],
                lasts=[3.30],
            )
            puts = make_chain_df([])
            mock_chain = MagicMock(calls=calls, puts=puts)

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                mock_ticker = MagicMock()
                mock_ticker.option_chain.return_value = mock_chain
                mock_ticker_cls.return_value = mock_ticker

                result = sut.fetch_quotes([occ])

            quote = result[occ]
            assert quote is not None
            assert quote.symbol == occ
            assert quote.bid_price == Money.mint(3.20)
            assert quote.ask_price == Money.mint(3.45)
            assert quote.last_price == Money.mint(3.30)
            assert quote.bid_size == 0
            assert quote.ask_size == 0
            mock_ticker.option_chain.assert_called_once_with("2025-01-17")

        def test_only_bid_missing_uses_zero(self, sut):
            occ = "AAPL250117C00150000"
            yf_symbol = sc.to_symbol(sc.to_option(occ))

            calls = make_chain_df([yf_symbol], asks=[2.50], bids=[None])
            puts = make_chain_df([])
            mock_chain = MagicMock(calls=calls, puts=puts)

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                mock_ticker_cls.return_value.option_chain.return_value = mock_chain
                result = sut.fetch_quotes([occ])

            quote = result[occ]
            assert quote is not None
            assert quote.bid_price == Money.zero()
            assert quote.ask_price == Money.mint(2.50)

        def test_only_ask_missing_uses_zero(self, sut):
            occ = "AAPL250117C00150000"
            yf_symbol = sc.to_symbol(sc.to_option(occ))

            calls = make_chain_df([yf_symbol], asks=[None], bids=[1.75])
            puts = make_chain_df([])
            mock_chain = MagicMock(calls=calls, puts=puts)

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                mock_ticker_cls.return_value.option_chain.return_value = mock_chain
                result = sut.fetch_quotes([occ])

            quote = result[occ]
            assert quote is not None
            assert quote.bid_price == Money.mint(1.75)
            assert quote.ask_price == Money.zero()

        def test_puts_and_calls_in_same_chain(self, sut):
            call_occ = "AAPL250117C00150000"
            put_occ = "AAPL250117P00150000"

            yf_call = sc.to_symbol(sc.to_option(call_occ))
            yf_put = sc.to_symbol(sc.to_option(put_occ))

            calls = make_chain_df([yf_call], asks=[3.25], bids=[3.10])
            puts = make_chain_df([yf_put], asks=[2.80], bids=[2.65])
            mock_chain = MagicMock(calls=calls, puts=puts)

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                mock_ticker_cls.return_value.option_chain.return_value = mock_chain
                result = sut.fetch_quotes([call_occ, put_occ])

            assert result[call_occ].ask_price == Money.mint(3.25)
            assert result[put_occ].ask_price == Money.mint(2.80)

        def test_multiple_underlyings(self, sut):
            occ_aapl = "AAPL250117C00150000"
            occ_msft = "MSFT250117C00400000"

            yf_aapl = sc.to_symbol(sc.to_option(occ_aapl))
            yf_msft = sc.to_symbol(sc.to_option(occ_msft))

            chain_aapl = MagicMock(
                calls=make_chain_df([yf_aapl], asks=[2.10], bids=[2.00]),
                puts=make_chain_df([]),
            )
            chain_msft = MagicMock(
                calls=make_chain_df([yf_msft], asks=[4.50], bids=[4.40]),
                puts=make_chain_df([]),
            )

            def ticker_factory(ticker: str):
                mock = MagicMock()
                mock.option_chain.return_value = chain_aapl if ticker == "AAPL" else chain_msft
                return mock

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker", side_effect=ticker_factory):
                result = sut.fetch_quotes([occ_aapl, occ_msft])

            assert result[occ_aapl].ask_price == Money.mint(2.10)
            assert result[occ_msft].ask_price == Money.mint(4.50)


class TestFetchAskPrices:

    def test_return_is_float_when_success(self, sut):
        occ = "AAPL250117C00150000"
        yf_symbol = sc.to_symbol(sc.to_option(occ))

        calls = make_chain_df([yf_symbol], asks=[3.45], bids=[3.20])
        puts = make_chain_df([])
        mock_chain = MagicMock(calls=calls, puts=puts)

        with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.option_chain.return_value = mock_chain
            result = sut.fetch_ask_prices([occ])

        assert result == {occ: 3.45}

    def test_return_is_none_when_failure(self, sut):
        result = sut.fetch_ask_prices(["GARBAGE"])
        assert result == {"GARBAGE": None}


class TestFetchBidPrices:

    def test_return_is_float_when_success(self, sut):
        occ = "AAPL250117C00150000"
        yf_symbol = sc.to_symbol(sc.to_option(occ))

        calls = make_chain_df([yf_symbol], asks=[3.45], bids=[3.20])
        puts = make_chain_df([])
        mock_chain = MagicMock(calls=calls, puts=puts)

        with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.option_chain.return_value = mock_chain
            result = sut.fetch_bid_prices([occ])

        assert result == {occ: 3.20}

    def test_return_is_none_when_failure(self, sut):
        result = sut.fetch_bid_prices(["GARBAGE"])
        assert result == {"GARBAGE": None}
