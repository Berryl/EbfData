"""
YFinance implementation of OptionPriceFetcher.
"""
import logging

import pandas as pd
import yfinance as yf
from ebf_trading.domain.value_objects.option_specific.option import Option
from ebf_trading.domain.value_objects.option_specific.symbol_conversion import symbol_converter as sc

from ebf_data.excel.pricing.option_price_fetcher import OptionPriceFetcher

logger = logging.getLogger(__name__)


class YFinanceOptionFetcher(OptionPriceFetcher):
    """
    Fetches current option ask prices from Yahoo Finance via yfinance.

    Ask prices are only available during trading hours (9:30am-4pm ET)
    and carry approximately a 15-minute delay.
    """

    def fetch_ask_prices(self, contracts: list[Option]) -> dict[str, float | None]:
        """
        Fetch ask prices for the given Option contracts.

        Groups by underlying ticker and expiration to minimize API calls —
        one option_chain() call per ticker+expiration combination.
        Returns a dict keyed by OCC symbol string.
        """
        result: dict[str, float | None] = {}

        # Group by (ticker, expiry_str) to batch API calls
        groups: dict[tuple[str, str], list[Option]] = {}
        for contract in contracts:
            key = (contract.ticker_symbol, str(contract.expiration))
            groups.setdefault(key, []).append(contract)

        for (ticker, expiry), group in groups.items():
            try:
                chain = yf.Ticker(ticker).option_chain(expiry)
                all_contracts = pd.concat([chain.calls, chain.puts], ignore_index=True)

                for contract in group:
                    occ = sc.to_symbol(contract)
                    all_contracts: pd.DataFrame = pd.concat([chain.calls, chain.puts], ignore_index=True)
                    match = all_contracts[(all_contracts["contractSymbol"] == occ)]
                    if match.empty:
                        logger.warning(f"No contract found in chain for {occ!r}")
                        result[occ] = None
                        continue
                    ask = match.iloc[0]["ask"]
                    result[occ] = float(ask) if pd.notna(ask) else None

            except Exception as e:
                logger.error(f"Failed to fetch option chain for {ticker} expiry={expiry}: {e}")
                for contract in group:
                    result[sc.to_symbol(contract)] = None

        return result
