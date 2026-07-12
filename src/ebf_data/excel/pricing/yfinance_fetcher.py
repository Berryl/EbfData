"""
yFinance implementation of a PriceFetcher.

Primary method: yf.Tickers.info (best for current/last price).
Fallback: yf.download() if the primary method fails entirely.

"""
import logging

import pandas as pd
import yfinance as yf

from ebf_data.excel.pricing.price_fetcher import PriceFetcher

logger = logging.getLogger(__name__)


class YFinanceFetcher(PriceFetcher):

    def fetch_prices(self, tickers: list[str]) -> dict[str, float | None]:
        """
        Fetch the most recent price for each ticker via yFinance.

        Returns dict mapping ticker -> price (float) or None if unavailable.
        """
        if not tickers:
            return {}

        prices: dict[str, float | None] = {}
        failed: list[str] = []

        # === PRIMARY METHOD: yf.Tickers.info ===
        try:
            yftickers = yf.Tickers(" ".join(tickers))
            for ticker in tickers:
                try:
                    info = yftickers.tickers[ticker].info
                    price = (
                        info.get("currentPrice")
                        or info.get("regularMarketPrice")
                        or info.get("previousClose")
                    )
                    prices[ticker] = float(price) if price is not None else None
                except Exception as e:
                    logger.warning(f"Could not get price info for {ticker}: {e}")
                    prices[ticker] = None
                    failed.append(ticker)

        except Exception as e:
            logger.warning(f"yFinance Tickers failed ({e}), falling back to download...")

            # === FALLBACK: yf.download() ===
            try:
                data: pd.DataFrame = yf.download(
                    tickers=tickers,
                    period="1d",
                    interval="1m",
                    group_by="ticker",
                    auto_adjust=True,
                    prepost=True,    # include after-hours data if available
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

                    except Exception as inner_e:
                        logger.warning(f"Could not extract price for {ticker}: {inner_e}")
                        prices[ticker] = None
                        failed.append(ticker)

            except Exception as download_e:
                logger.error(f"yFinance download fallback also failed: {download_e}")
                prices = {t: None for t in tickers}

        if failed:
            logger.warning(f"Failed to fetch prices for: {', '.join(failed)}")

        return prices

