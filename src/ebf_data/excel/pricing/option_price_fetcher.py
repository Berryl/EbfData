"""
Abstract base class for options-price fetchers.
"""
from abc import ABC, abstractmethod


class OptionPriceFetcher(ABC):
    """
    Base class for anything that can fetch current ask prices for a list
    of OCC option symbols. Subclass and implement fetch_ask_prices() to
    provide a concrete options price source.
    """

    @abstractmethod
    def fetch_ask_prices(self, occ_symbols: list[str]) -> dict[str, float | None]:
        """
        Fetch current ask prices for the given OCC option symbols.

        Returns a dict keyed by OCC symbol. A None value means the price
        could not be determined for that symbol.
        """
        ...