"""
Abstract base class for options-price fetchers.
"""
from abc import ABC, abstractmethod
from decimal import InvalidOperation

import pandas as pd
from ebf_domain.money.money import Money, to_money
from ebf_trading.domain.value_objects.quotes.quote import Quote


class OptionPriceFetcher(ABC):
    """
    Base class for anything that can fetch current prices for a list of OCC option symbols.
    """

    @abstractmethod
    def fetch_quotes(self, occ_symbols: list[str]) -> dict[str, Quote | None]:
        """
        Fetch Level-1 quotes for the given OCC option symbols.

        Returns a dict keyed by the exact OCC strings that were passed in.
        A None value means no usable quote could be obtained for that symbol.
        """
        ...

    def fetch_ask_prices(self, occ_symbols: list[str]) -> dict[str, float | None]:
        """
        Convenience wrapper – returns only the ask price (as float).
        """
        quotes = self.fetch_quotes(occ_symbols)
        return {
            occ: (float(q.ask_price.amount) if q is not None else None)
            for occ, q in quotes.items()
        }

    def fetch_bid_prices(self, occ_symbols: list[str]) -> dict[str, float | None]:
        """
        Convenience wrapper – returns only the bid price (as float).
        """
        quotes = self.fetch_quotes(occ_symbols)
        return {
            occ: (float(q.bid_price.amount) if q is not None else None)
            for occ, q in quotes.items()
        }

    @staticmethod
    def _to_money(value) -> Money | None:
        if value is None or pd.isna(value):
            return None
        try:
            return to_money(value)
        except (ValueError, TypeError, InvalidOperation, ArithmeticError):
            return None