from unittest.mock import MagicMock, patch, PropertyMock
import pandas as pd
import pytest

from ebf_data.excel.pricing.yfinance_fetcher import YFinanceFetcher


@pytest.fixture
def sut() -> YFinanceFetcher:
    return YFinanceFetcher()


def make_fast_info(**kwargs) -> MagicMock:
    info = MagicMock()
    # Support both attribute and .get() access
    for k, v in kwargs.items():
        setattr(info, k, v)
    info.get = lambda key, default=None: kwargs.get(key, default)
    return info


def make_download_df(tickers: list[str], closes: dict[str, list[float | None]]) -> pd.DataFrame:
    """Reliable multi-ticker (or single) download-shaped DataFrame."""
    if len(tickers) == 1:
        t = tickers[0]
        return pd.DataFrame({"Close": closes[t]})

    # MultiIndex columns: (ticker, OHLCV)
    columns = pd.MultiIndex.from_product([tickers, ["Open", "High", "Low", "Close", "Volume"]])
    data = {}
    length = max(len(v) for v in closes.values())

    for t in tickers:
        series = closes.get(t, [None] * length)
        # pad if necessary
        series = list(series) + [None] * (length - len(series))
        data[(t, "Open")] = [1.0] * length
        data[(t, "High")] = [1.0] * length
        data[(t, "Low")] = [1.0] * length
        data[(t, "Close")] = series
        data[(t, "Volume")] = [100] * length

    return pd.DataFrame(data)


def make_ticker_that_raises():
    """Return a Ticker mock whose .fast_info access raises."""
    m = MagicMock()
    type(m).fast_info = PropertyMock(side_effect=RuntimeError("fast_info failed"))
    return m


class TestYFinanceFetcher:

    # ... keep the successful primary-path tests as they were ...

    class TestPrimaryPathFastInfo:

        def test_exception_in_fast_info_is_handled(self, sut):
            with patch("ebf_data.excel.pricing.yfinance_fetcher.yf.Ticker", side_effect=lambda t: make_ticker_that_raises()):
                with patch("ebf_data.excel.pricing.yfinance_fetcher.yf.download", side_effect=Exception("download dead")):
                    result = sut.fetch_prices(["AAPL"])

            assert result == {"AAPL": None}

    class TestFallbackDownload:

        def test_download_used_when_all_fast_info_fail(self, sut):
            with patch("ebf_data.excel.pricing.yfinance_fetcher.yf.Ticker", side_effect=lambda t: make_ticker_that_raises()):
                df = make_download_df(["AAPL"], {"AAPL": [100.0, 101.5]})
                with patch("ebf_data.excel.pricing.yfinance_fetcher.yf.download", return_value=df):
                    result = sut.fetch_prices(["AAPL"])

            assert result == {"AAPL": 101.5}

        def test_download_multi_ticker(self, sut):
            with patch("ebf_data.excel.pricing.yfinance_fetcher.yf.Ticker", side_effect=lambda t: make_ticker_that_raises()):
                df = make_download_df(
                    ["AAPL", "MSFT"],
                    {"AAPL": [150.0], "MSFT": [300.0]},
                )
                with patch("ebf_data.excel.pricing.yfinance_fetcher.yf.download", return_value=df):
                    result = sut.fetch_prices(["AAPL", "MSFT"])

            assert result == {"AAPL": 150.0, "MSFT": 300.0}

        def test_download_also_fails(self, sut):
            with patch("ebf_data.excel.pricing.yfinance_fetcher.yf.Ticker", side_effect=lambda t: make_ticker_that_raises()):
                with patch("ebf_data.excel.pricing.yfinance_fetcher.yf.download", side_effect=Exception("download dead")):
                    result = sut.fetch_prices(["AAPL", "MSFT"])

            assert result == {"AAPL": None, "MSFT": None}

    class TestMixedResults:

        def test_some_succeed_some_fail_on_primary(self, sut):
            def ticker_side_effect(symbol):
                if symbol == "AAPL":
                    m = MagicMock()
                    m.fast_info = make_fast_info(lastPrice=150.0)
                    return m
                return make_ticker_that_raises()

            with patch("ebf_data.excel.pricing.yfinance_fetcher.yf.Ticker", side_effect=ticker_side_effect):
                result = sut.fetch_prices(["AAPL", "BAD"])

            assert result["AAPL"] == 150.0
            assert result["BAD"] is None

@pytest.mark.integration
class TestLiveIntegration:
    def test_can_fetch_live_data(self, sut):
        """Hit real Yahoo Finance – run manually when you want to check connectivity."""
        result = sut.fetch_prices(["AAPL", "MSFT", "INVALIDTICKERXYZ"])

        assert result["AAPL"] is not None and result["AAPL"] > 0
        assert result["MSFT"] is not None and result["MSFT"] > 0
        assert result["INVALIDTICKERXYZ"] is None

        print("Live prices:", result)  # handy when running manually