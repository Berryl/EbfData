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
# Silence noisy third-party loggers
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("peewee").setLevel(logging.WARNING)


class YFinanceOptionFetcher(OptionPriceFetcher):
    """
    Fetches current option ask prices from Yahoo Finance via yfinance.

    Ask prices are only available during trading hours (9:30am-4pm ET)
    and carry approximately a 15-minute delay.
    """

    def fetch_ask_prices(self, occ_symbols: list[str]) -> dict[str, float | None]:
        """
        Fetch ask prices for the given OCC option symbols.

        Groups by underlying ticker and expiration to minimize API calls -
        one option_chain() call per ticker+expiration combination. The
        returned dict is always keyed by the exact strings passed in, never
        a re-derived/reformatted symbol - sc.to_symbol() is used internally
        only to match against YFinance's own contractSymbol formatting,
        which may not be byte-identical to the request string.
        """
        result: dict[str, float | None] = {}
        if not occ_symbols:
            return result

        # Parse OCC → Option (skip any that fail)
        symbol_to_contract: dict[str, Option] = {}
        for occ in occ_symbols:
            try:
                symbol_to_contract[occ] = sc.to_option(occ)
            except ValueError as e:
                logger.warning(f"Could not parse OCC symbol {occ!r}: {e}")
                result[occ] = None

        if not symbol_to_contract:
            return result

        # Group by (ticker, expiration) to batch option_chain() calls.
        groups: dict[tuple[str, str], list[str]] = {}
        for occ, contract in symbol_to_contract.items():
            ticker = contract.underlying.value
            expiry = contract.expiration.date.isoformat()

            key = (ticker, expiry)
            groups.setdefault(key, []).append(occ)

        for (ticker, expiry), group_symbols in groups.items():
            try:
                chain = yf.Ticker(ticker).option_chain(expiry)
                all_contracts = pd.concat([chain.calls, chain.puts], ignore_index=True)

                for occ in group_symbols:
                    contract = symbol_to_contract[occ]
                    yf_symbol = sc.to_symbol(contract)  # default = unpadded OCC
                    match = all_contracts[all_contracts["contractSymbol"] == yf_symbol] # type: ignore[index]

                    if match.empty:
                        logger.warning(f"No contract found in chain for {occ!r} (yfinance symbol {yf_symbol!r})")
                        result[occ] = None
                        continue

                    ask = match.iloc[0]["ask"]
                    result[occ] = float(ask) if pd.notna(ask) else None

            except Exception as e:
                logger.error(f"Failed to fetch option chain for {ticker} expiry={expiry}: {e}")
                for occ in group_symbols:
                    result[occ] = None

        return result