"""
YFinance implementation of OptionPriceFetcher.
"""
import logging

import pandas as pd
import yfinance as yf
from ebf_domain.money.money import Money
from ebf_trading.domain.date_time.market_days import get_timestamp
from ebf_trading.domain.value_objects.option_specific.option import Option
from ebf_trading.domain.value_objects.option_specific.symbol_conversion import symbol_converter as sc
from ebf_trading.domain.value_objects.quotes.quote import Quote

from ebf_data.excel.pricing.option_price_fetcher import OptionPriceFetcher

logger = logging.getLogger(__name__)

# Silence noisy third-party loggers
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("peewee").setLevel(logging.WARNING)


class YFinanceOptionFetcher(OptionPriceFetcher):
    """
    Fetches current option quotes (bid/ask) from Yahoo Finance via yfinance.

    Quotes are only available during trading hours (9:30am-4pm ET)
    and carry approximately a 15-minute delay.
    """

    def fetch_quotes(self, occ_symbols: list[str]) -> dict[str, Quote | None]:
        """
        Fetch Level-1 quotes for the given OCC option symbols.

        Groups by underlying ticker and expiration to minimize API calls –
        one option_chain() call per ticker+expiration combination.

        The returned dict is always keyed by the exact strings passed in.
        Returns None only when both bid and ask are missing (or the contract
        cannot be resolved).
        """
        result: dict[str, Quote | None] = {}
        if not occ_symbols:
            return result

        # Parse OCC → Option
        symbol_to_contract: dict[str, Option] = {}
        for occ in occ_symbols:
            try:
                symbol_to_contract[occ] = sc.to_option(occ)
            except ValueError as e:
                logger.warning(f"Could not parse OCC symbol {occ!r}: {e}")
                result[occ] = None

        if not symbol_to_contract:
            return result

        # Group by (ticker, expiration)
        groups: dict[tuple[str, str], list[str]] = {}
        for occ, contract in symbol_to_contract.items():
            ticker = contract.underlying.value
            expiration = contract.expiration.date.isoformat()
            key = (ticker, expiration)
            groups.setdefault(key, []).append(occ)

        now = get_timestamp()

        for (ticker, expiry), group_symbols in groups.items():
            try:
                chain = yf.Ticker(ticker).option_chain(expiry)
                all_contracts = pd.concat([chain.calls, chain.puts], ignore_index=True)

                for occ in group_symbols:
                    contract = symbol_to_contract[occ]
                    yf_symbol = sc.to_symbol(contract)
                    match = all_contracts[all_contracts["contractSymbol"] == yf_symbol]  # type: ignore[index]

                    if match.empty:
                        logger.warning(f"No contract found in chain for {occ!r} (yfinance symbol {yf_symbol!r})")
                        result[occ] = None
                        continue

                    row = match.iloc[0]
                    bid = self._to_money(row.get("bid"))
                    ask = self._to_money(row.get("ask"))

                    # Both sides missing → no usable quote
                    if bid is None and ask is None:
                        result[occ] = None
                        continue

                    # One side missing → treat as zero (rare but better than discarding)
                    bid = bid if bid is not None else Money.zero()
                    ask = ask if ask is not None else Money.zero()

                    last = self._to_money(row.get("lastPrice"))

                    result[occ] = Quote(
                        symbol=occ,
                        bid_price=bid,
                        bid_size=0,          # yfinance does not provide reliable size
                        ask_price=ask,
                        ask_size=0,
                        timestamp=now,
                        last_price=last,
                        last_size=None,
                    )

            except Exception as e:
                logger.error(f"Failed to fetch option chain for {ticker} expiry={expiry}: {e}")
                for occ in group_symbols:
                    result[occ] = None

        return result