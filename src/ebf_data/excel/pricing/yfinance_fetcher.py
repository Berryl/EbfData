"""
yfinance implementation of a PriceFetcher.

Primary method : Ticker.fast_info  (fast, lightweight)
Fallback       : yf.download()     (if the primary path fails completely)
"""
import logging
from typing import Any

import pandas as pd
import yfinance as yf

from ebf_data.excel.pricing.price_fetcher import PriceFetcher

logger = logging.getLogger(__name__)

# Silence noisy third-party loggers
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("peewee").setLevel(logging.WARNING)


class YFinanceFetcher(PriceFetcher):

    def fetch_prices(self, tickers: list[str]) -> dict[str, float | None]:
        """
        Fetch the most recent price for each ticker via yfinance.

        Returns a dict mapping ticker → price (float) or None if unavailable.
        """
        if not tickers:
            return {}

        prices: dict[str, float | None] = {}
        failed: list[str] = []

        # ------------------------------------------------------------------
        # PRIMARY: fast_info (preferred)
        # ------------------------------------------------------------------
        try:
            for ticker in tickers:
                try:
                    info = yf.Ticker(ticker).fast_info
                    price = self._extract_price(info)
                    prices[ticker] = price
                    if price is None:
                        failed.append(ticker)
                except Exception as e:
                    logger.warning(f"fast_info failed for {ticker}: {e}")
                    prices[ticker] = None
                    failed.append(ticker)

            # If we got at least some prices, we're done
            if any(p is not None for p in prices.values()):
                if failed:
                    logger.warning(f"Failed to fetch prices for: {', '.join(failed)}")
                return prices

            logger.warning("All fast_info calls returned no usable price – falling back to download")

        except Exception as e:
            logger.warning(f"Primary fast_info path failed entirely ({e}), falling back to download")

        # ------------------------------------------------------------------
        # FALLBACK: yf.download
        # ------------------------------------------------------------------
        return self._fetch_via_download(tickers)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_price(info: Any) -> float | None:
        """
        Pull the best available last price from a fast_info (or info) object.
        """
        for key in (
            "lastPrice",
            "last_price",          # some versions
            "regularMarketPrice",
            "currentPrice",
            "previousClose",
            "previous_close",
        ):
            value = info.get(key) if hasattr(info, "get") else getattr(info, key, None)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return None

    def _fetch_via_download(self, tickers: list[str]) -> dict[str, float | None]:
        prices: dict[str, float | None] = {t: None for t in tickers}

        try:
            data: pd.DataFrame = yf.download(
                tickers=tickers,
                period="1d",
                interval="1m",
                group_by="ticker",
                auto_adjust=True,
                prepost=True,
                progress=False,
                threads=True,
            )

            for ticker in tickers:
                try:
                    if len(tickers) == 1 and not isinstance(data.columns, pd.MultiIndex):
                        close_series = data["Close"]
                    else:
                        close_series = data[ticker]["Close"]

                    close = close_series.dropna()
                    prices[ticker] = float(close.iloc[-1]) if not close.empty else None

                except Exception as e:
                    logger.warning(f"Could not extract price for {ticker} from download: {e}")
                    prices[ticker] = None

        except Exception as e:
            logger.error(f"yfinance download fallback also failed: {e}")

        failed = [t for t, p in prices.items() if p is None]
        if failed:
            logger.warning(f"Failed to fetch prices for: {', '.join(failed)}")

        return prices