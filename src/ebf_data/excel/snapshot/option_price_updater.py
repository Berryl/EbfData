"""
Option price fetcher for snapshot positions.
"""
import logging
import time
from enum import StrEnum, auto
from typing import Literal

from ebf_trading.domain.value_objects.option_specific.symbol_conversion import symbol_converter as sc

from ebf_data.excel.pricing.option_price_fetcher import OptionPriceFetcher
from ebf_data.excel.pricing.pricing_helpers import PriceUpdateResult, SymbolPriceOutcome
from ebf_data.excel.pricing.yfinance_option_fetcher import YFinanceOptionFetcher
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

logger = logging.getLogger(__name__)

BidOrAsk = Literal["ask", "bid"]


class OptionType(StrEnum):
    SHORT_CALL = auto()
    SHORT_PUT = auto()
    LONG_CALL = auto()
    LONG_PUT = auto()


def get_outcomes(
        results: dict[OptionType, tuple[PriceUpdateResult, list[SymbolPriceOutcome]]], t: OptionType | None = None,
) -> list[SymbolPriceOutcome]:
    """
    Extract outcomes for one option type or for all types when *t* is None.
    """
    if t is not None:
        return results[t][1]

    all_outcomes: list[SymbolPriceOutcome] = []
    for t in OptionType:
        all_outcomes.extend(results[t][1])
    return all_outcomes


class OptionPriceUpdater:
    """
    Fetches current option prices (ask for shorts, bid for longs)
    using the injected OptionPriceFetcher.
    Returns per-row outcomes for PriceExporter – does not touch the workbook.
    """

    SC_SYMBOL_COLUMN = SnapshotTable.SC_SYMBOL_COLUMN
    SP_SYMBOL_COLUMN = SnapshotTable.SP_SYMBOL_COLUMN
    LC_SYMBOL_COLUMN = SnapshotTable.LC_SYMBOL_COLUMN
    LP_SYMBOL_COLUMN = SnapshotTable.LP_SYMBOL_COLUMN

    def __init__(self, snapshot: SnapshotTable, fetcher: OptionPriceFetcher | None = None) -> None:
        self._snapshot = snapshot
        self._fetcher = fetcher or YFinanceOptionFetcher()

    def fetch_short_call_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        return self.fetch_all_option_prices()[OptionType.SHORT_CALL]

    def fetch_short_put_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        return self.fetch_all_option_prices()[OptionType.SHORT_PUT]

    def fetch_long_call_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        return self.fetch_all_option_prices()[OptionType.LONG_CALL]

    def fetch_long_put_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        return self.fetch_all_option_prices()[OptionType.LONG_PUT]

    def fetch_all_option_prices(self) -> dict[OptionType, tuple[PriceUpdateResult, list[SymbolPriceOutcome]]]:
        """
        Fetch prices for all four option types in a single pass.

        Returns a dict keyed by OptionType.
        """
        t0 = time.monotonic()
        self._snapshot.refresh()
        df = self._snapshot.df

        option_types: dict[OptionType, tuple[str, BidOrAsk]] = {
            OptionType.SHORT_CALL: (self.SC_SYMBOL_COLUMN, "ask"),
            OptionType.SHORT_PUT: (self.SP_SYMBOL_COLUMN, "ask"),
            OptionType.LONG_CALL: (self.LC_SYMBOL_COLUMN, "bid"),
            OptionType.LONG_PUT: (self.LP_SYMBOL_COLUMN, "bid"),
        }

        # 1. Collect symbols + row indices per option type
        option_type_data: dict[OptionType, dict[str, list[int]]] = {}
        all_symbols: set[str] = set()

        for ot, (col, _) in option_types.items():
            symbol_to_indices: dict[str, list[int]] = {}

            if col in df.columns:
                active = df[df[col].notna() & (df[col] != "")]
                for idx, row in active.iterrows():
                    symbol = str(row[col]).strip()
                    try:
                        sc.to_option(symbol)
                    except ValueError as e:
                        logger.warning(f"Skipping unparseable OCC symbol {symbol!r}: {e}")
                        continue

                    symbol_to_indices.setdefault(symbol, []).append(idx)
                    all_symbols.add(symbol)

            option_type_data[ot] = symbol_to_indices

        # 2. Single network call
        t1 = time.monotonic()
        quotes = self._fetcher.fetch_quotes(list(all_symbols)) if all_symbols else {}
        fetch_time = time.monotonic() - t1

        # 3. Build results per ot
        results: dict[OptionType, tuple[PriceUpdateResult, list[SymbolPriceOutcome]]] = {}

        for ot, (col, price_side) in option_types.items():
            result = PriceUpdateResult()
            outcomes: list[SymbolPriceOutcome] = []
            failed: list[str] = []

            symbol_to_indices = option_type_data[ot]
            result.total_symbols = len(symbol_to_indices)
            result.price_fetching_time = fetch_time

            for symbol, indices in symbol_to_indices.items():
                quote = quotes.get(symbol)
                price: float | None = None

                if quote is not None:
                    money = quote.ask_price if price_side == "ask" else quote.bid_price
                    price = float(money.amount)

                success = price is not None
                if not success:
                    logger.warning(f"No {price_side} price available for {symbol}")
                    failed.append(symbol)

                for idx in indices:
                    raw_symbol = str(df.loc[idx, col])  # noqa type: ignore[arg-type]
                    outcomes.append(
                        SymbolPriceOutcome(symbol=raw_symbol, price=price, success=success)
                    )

            result.failed = failed
            result.total_time = time.monotonic() - t0
            results[ot] = (result, outcomes)

            if result.total_symbols:
                logger.info(
                    f"[{ot}] {result.updated_symbols}/{result.total_symbols} "
                    f"updated in {result.total_time:.1f}s"
                )

        return results
