"""
Price fetcher base class and run result types.
"""
from abc import ABC, abstractmethod


class PriceFetcher(ABC):
    """
    Base class for anything that can fetch prices for a list of tickers.

    Subclass and implement fetch_prices() to provide a concrete price
    source. The caller decides what to do with None values - this class
    makes no assumptions about how missing prices are handled.
    """

    @abstractmethod
    def fetch_prices(self, tickers: list[str]) -> dict[str, float | None]:
        ...


