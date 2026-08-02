from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from ebf_trading.domain.value_objects.option_specific.symbol_conversion import symbol_converter as sc

from ebf_data.excel.pricing.option_price_fetcher import OptionPriceFetcher
from ebf_data.excel.pricing.yfinance_option_fetcher import YFinanceOptionFetcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_chain_df(contract_symbols: list[str], asks: list[float | None]) -> pd.DataFrame:
    """Minimal DataFrame that mimics yfinance option_chain calls/puts."""
    return pd.DataFrame({
        "contractSymbol": contract_symbols,
        "ask": asks,
    })


@pytest.fixture
def fetcher():
    return YFinanceOptionFetcher()


class TestYFinanceOptionFetcher:

    @pytest.fixture
    def sut(self) -> OptionPriceFetcher:
        return YFinanceOptionFetcher()

    class TestWhenUnsuccessful:

        def test_when_passed_an_empty_list_the_return_is_an_empty_dict(self, sut):
            assert sut.fetch_ask_prices([]) == {}

        def test_unparseable_symbols_are_valued_as_none(self, sut):
            result = sut.fetch_ask_prices(["INVALID1", "NOT-AN-OCC", "SPY"])
            assert result == {
                "INVALID1": None,
                "NOT-AN-OCC": None,
                "SPY": None,
            }

        def test_a_symbol_without_a_matching_contract_returns_none(self, sut):
            occ = "AAPL250117C00150000"
            yf_symbol = sc.to_symbol(sc.to_option(occ))

            # Chain contains a different contract
            calls = make_chain_df(["AAPL250117C00200000"], [5.0])
            puts = make_chain_df([], [])
            mock_chain = MagicMock(calls=calls, puts=puts)

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                mock_ticker_cls.return_value.option_chain.return_value = mock_chain
                result = sut.fetch_ask_prices([occ])

            assert result == {occ: None}

        def test_nan_ask_becomes_none(self, sut):
            occ = "AAPL250117C00150000"
            yf_symbol = sc.to_symbol(sc.to_option(occ))

            calls = make_chain_df([yf_symbol], [float("nan")])
            puts = make_chain_df([], [])
            mock_chain = MagicMock(calls=calls, puts=puts)

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                mock_ticker_cls.return_value.option_chain.return_value = mock_chain
                result = sut.fetch_ask_prices([occ])

            assert result == {occ: None}

        def test_option_chain_exception_sets_whole_group_to_none(self, sut):
            symbols = ["AAPL250117C00150000", "AAPL250117P00150000", ]

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                mock_ticker_cls.return_value.option_chain.side_effect = RuntimeError("Yahoo is down")
                result = sut.fetch_ask_prices(symbols)

            assert result == {s: None for s in symbols}

    class TestWhenSuccessful:

        def test_can_fetch_single_group(self, sut):
            # Real OCC symbol – will be parsed by the real converter
            occ = "AAPL250117C00150000"
            expected_yf_symbol = sc.to_symbol(sc.to_option(occ))  # should be identical

            calls = make_chain_df([expected_yf_symbol], [3.45])
            puts = make_chain_df([], [])
            mock_chain = MagicMock(calls=calls, puts=puts)

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
                mock_ticker = MagicMock()
                mock_ticker.option_chain.return_value = mock_chain
                mock_ticker_cls.return_value = mock_ticker

                result = sut.fetch_ask_prices([occ])

            assert result == {occ: 3.45}
            # Verify the correct expiry was requested
            mock_ticker.option_chain.assert_called_once_with("2025-01-17")

        def test_can_fetch_multiple_groups(self, sut):
            """Different tickers → independent option_chain calls."""
            occ_1 = "AAPL250117C00150000"
            occ_2 = "MSFT250117C00400000"

            yf_1 = sc.to_symbol(sc.to_option(occ_1))
            yf_2 = sc.to_symbol(sc.to_option(occ_2))

            chain_1 = MagicMock(
                calls=make_chain_df([yf_1], [2.10]),
                puts=make_chain_df([], []),
            )
            chain_2 = MagicMock(
                calls=make_chain_df([yf_2], [4.50]),
                puts=make_chain_df([], []),
            )

            def ticker_factory(ticker: str):
                mock = MagicMock()
                if ticker == "AAPL":
                    mock.option_chain.return_value = chain_1
                else:
                    mock.option_chain.return_value = chain_2
                return mock

            with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker", side_effect=ticker_factory):
                result = sut.fetch_ask_prices([occ_1, occ_2])

            assert result == {occ_1: 2.10, occ_2: 4.50, }


def test_mixed_valid_and_invalid_symbols(fetcher):
    valid = "AAPL250117C00150000"
    invalid = "GARBAGE"

    yf_symbol = sc.to_symbol(sc.to_option(valid))
    calls = make_chain_df([yf_symbol], [1.23])
    puts = make_chain_df([], [])
    mock_chain = MagicMock(calls=calls, puts=puts)

    with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.option_chain.return_value = mock_chain
        result = fetcher.fetch_ask_prices([valid, invalid])

    assert result == {valid: 1.23, invalid: None}


def test_puts_and_calls_in_same_chain(fetcher):
    """Both a call and a put for the same underlying+expiry."""
    call_occ = "AAPL250117C00150000"
    put_occ = "AAPL250117P00150000"

    yf_call = sc.to_symbol(sc.to_option(call_occ))
    yf_put = sc.to_symbol(sc.to_option(put_occ))

    calls = make_chain_df([yf_call], [3.25])
    puts = make_chain_df([yf_put], [2.80])
    mock_chain = MagicMock(calls=calls, puts=puts)

    with patch("ebf_data.excel.pricing.yfinance_option_fetcher.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.option_chain.return_value = mock_chain
        result = fetcher.fetch_ask_prices([call_occ, put_occ])

    assert result == {
        call_occ: 3.25,
        put_occ: 2.80,
    }
