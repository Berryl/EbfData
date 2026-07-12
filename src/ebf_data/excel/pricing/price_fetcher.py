"""
Price fetcher base class and run result type.

These live in the pricing package rather than snapshot because they
are reusable across any table that needs price updating (snapshot,
cagr, etc.) and have no dependency on any specific table or data source.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PriceUpdateResult:
    """Summary of a single update_prices() run."""
    total_symbols: int = 0
    updated: int = 0
    failed: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_symbols == 0:
            return 0.0
        return self.updated / self.total_symbols


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