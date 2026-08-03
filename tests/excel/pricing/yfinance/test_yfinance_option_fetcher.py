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


class TestYFinanceOptionFetcher:

    @pytest.fixture(scope="module")
    def sut(self) -> OptionPriceFetcher:
        return YFinanceOptionFetcher()

    class TestFetchQuotes:
        class TestUnsuccessfulConditions:

            def test_when_passed_an_empty_list_the_return_is_an_empty_dict(self, sut):
                assert sut.fetch_quotes([]) == {}

            def test_unparseable_symbols_are_valued_as_none(self, sut):
                result = sut.fetch_quotes(["INVALID1", "NOT-AN-OCC", "SPY"])
                assert result == {"INVALID1": None, "NOT-AN-OCC": None, "SPY": None}

            def test_a_symbol_without_a_matching_contract_returns_none(self, sut):
                occ_target = "AAPL250117C00150000"
                occ_available = "AAPL250117C00200000"

                calls = make_chain_df([occ_available], asks=[5.0], bids=[4.8])
                puts = make_chain_df([], asks=[], bids=[])
                mock_chain = MagicMock(calls=calls, puts=puts)

                with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                    mock_ticker_cls.return_value.option_chain.return_value = mock_chain
                    result = sut.fetch_quotes([occ_target])

                assert result == {occ_target: None}

            def test_when_both_bid_and_ask__are_missing__then_return_is_none(self, sut):
                occ = "AAPL250117C00150000"
                yf_symbol = sc.to_symbol(sc.to_option(occ))

                calls = make_chain_df([yf_symbol], asks=[None], bids=[None])
                puts = make_chain_df([])
                mock_chain = MagicMock(calls=calls, puts=puts)

                with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                    mock_ticker_cls.return_value.option_chain.return_value = mock_chain
                    result = sut.fetch_quotes([occ])

                assert result == {occ: None}

            def test_an_option_chain_exception_sets_the_whole_group_to_none(self, sut):
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

            def test_when_only_the_bid_is_missing_then_the_bid_is_zero(self, sut):
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

            def test_when_only_the_ask_is_missing_then_the_ask_is_zero(self, sut):
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

            def test_can_fetch_puts_and_calls_in_same_chain(self, sut):
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

                call_quote = result[call_occ]
                put_quote = result[put_occ]

                assert call_quote is not None
                assert put_quote is not None

                assert call_quote.ask_price == Money.mint(3.25)
                assert put_quote.ask_price == Money.mint(2.80)

            def test_can_fetch_multiple_underlying_tickers(self, sut):
                occ1 = "AAPL250117C00150000"
                occ2 = "MSFT250117C00400000"

                yf1 = sc.to_symbol(sc.to_option(occ1))
                yf2 = sc.to_symbol(sc.to_option(occ2))

                chain1 = MagicMock(
                    calls=make_chain_df([yf1], asks=[2.10], bids=[2.00]),
                    puts=make_chain_df([]),
                )
                chain2 = MagicMock(
                    calls=make_chain_df([yf2], asks=[4.50], bids=[4.40]),
                    puts=make_chain_df([]),
                )

                def ticker_factory(ticker: str):
                    mock = MagicMock()
                    mock.option_chain.return_value = chain1 if ticker == "AAPL" else chain2
                    return mock

                with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker", side_effect=ticker_factory):
                    result = sut.fetch_quotes([occ1, occ2])

                occ1_quote = result[occ1]
                occ2_quote = result[occ2]

                assert occ1_quote is not None
                assert occ2_quote is not None

                assert occ1_quote.ask_price == Money.mint(2.10)
                assert occ2_quote.ask_price == Money.mint(4.50)

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

class TestLiveIntegration:

    @pytest.mark.integration
    def test_live_option_quotes_smoke(self):
        """
        Hit real Yahoo Finance for a couple of liquid option contracts.
        Run manually with: pytest -m integration -s
        """
        sut = YFinanceOptionFetcher()

        # Use contracts that are very likely to exist (adjust dates if needed)
        # Example: AAPL and SPY near-term calls – change the OCC strings to
        # currently listed expirations if these have already expired.
        symbols = [
            "AMZN260918C00200000",  # AMZN 18-Sep-2026 200 Call
            "INVALID-OCC-SYMBOL123",  # should return None
        ]

        result = sut.fetch_quotes(symbols)

        # Valid contracts should return a Quote with real prices
        q1 = result["AMZN260918C00200000"]

        assert q1 is not None
        assert isinstance(q1.bid_price, Money)
        assert isinstance(q1.ask_price, Money)
        assert q1.bid_price.amount >= 0
        assert q1.ask_price.amount >= 0

        assert q1 is not None

        # Invalid symbol must be None
        assert result["INVALID-OCC-SYMBOL123"] is None

        # Helpful when running manually
        print("\nLive option quotes:")
        for sym, q in result.items():
            if q:
                print(f"  {sym}: bid={q.bid_price}  ask={q.ask_price}  last={q.last_price}")
            else:
                print(f"  {sym}: None")