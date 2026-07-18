"""
Price fetcher base class and run result type.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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


@dataclass
class PriceUpdateResult:
    """Summary of a single pricing run."""
    total_symbols: int = 0
    updated_rows: int = 0
    failed: list[str] = field(default_factory=list)
    price_fetching_time: float = 0.0
    excel_updating_time: float = 0.0
    total_time: float = 0.0

    @property
    def updated_symbols(self) -> int:
        return self.total_symbols - len(self.failed)

    @property
    def success_rate(self) -> float:
        if self.total_symbols == 0:
            return 0.0
        return self.updated_symbols / self.total_symbols
