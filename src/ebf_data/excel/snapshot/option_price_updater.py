"""
Option price fetcher for snapshot positions.
"""
import logging
import time
from typing import Literal

from ebf_trading.domain.value_objects.option_specific.symbol_conversion import symbol_converter as sc

from ebf_data.excel.pricing.option_price_fetcher import OptionPriceFetcher
from ebf_data.excel.pricing.price_fetcher import PriceUpdateResult, SymbolPriceOutcome
from ebf_data.excel.pricing.yfinance_option_fetcher import YFinanceOptionFetcher
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

logger = logging.getLogger(__name__)

BidOrAsk = Literal["ask", "bid"]


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

    def __init__(self, snapshot: SnapshotTable,fetcher: OptionPriceFetcher | None = None) -> None:
        self._snapshot = snapshot
        self._fetcher = fetcher or YFinanceOptionFetcher()

    def fetch_short_call_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        return self.fetch_all_option_prices()["short_call"]

    def fetch_short_put_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        return self.fetch_all_option_prices()["short_put"]

    def fetch_long_call_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        return self.fetch_all_option_prices()["long_call"]

    def fetch_long_put_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        return self.fetch_all_option_prices()["long_put"]

    def fetch_all_option_prices(self) -> dict[str, tuple[PriceUpdateResult, list[SymbolPriceOutcome]]]:
        """
        Fetch prices for all four option sides in a single pass.

        Returns a dict keyed by side name:
            {
                "short_call": (PriceUpdateResult, list[SymbolPriceOutcome]),
                "short_put": (...),
                "long_call": (...),
                "long_put": (...),
            }
        """
        t0 = time.monotonic()
        self._snapshot.refresh()
        df = self._snapshot.df

        sides: dict[str, tuple[str, BidOrAsk]] = {
            "short_call": (self.SC_SYMBOL_COLUMN, "ask"),
            "short_put":  (self.SP_SYMBOL_COLUMN, "ask"),
            "long_call":  (self.LC_SYMBOL_COLUMN, "bid"),
            "long_put":   (self.LP_SYMBOL_COLUMN, "bid"),
        }

        # 1. Collect symbols + row indices per side
        side_data: dict[str, dict[str, list[int]]] = {}
        all_symbols: set[str] = set()

        for side_name, (col, _) in sides.items():
            symbol_to_indices: dict[str, list[int]] = {}

            if col in df.columns:
                active = df[df[col].notna() & (df[col] != "")]
                for idx, row in active.iterrows():
                    occ = str(row[col]).strip()
                    try:
                        sc.to_option(occ)  # validate
                    except ValueError as e:
                        logger.warning(f"Skipping unparseable OCC symbol {occ!r}: {e}")
                        continue

                    symbol_to_indices.setdefault(occ, []).append(idx)
                    all_symbols.add(occ)

            side_data[side_name] = symbol_to_indices

        # 2. Single network call
        t1 = time.monotonic()
        quotes = self._fetcher.fetch_quotes(list(all_symbols)) if all_symbols else {}
        fetch_time = time.monotonic() - t1

        # 3. Build results per side
        results: dict[str, tuple[PriceUpdateResult, list[SymbolPriceOutcome]]] = {}

        for side_name, (col, price_side) in sides.items():
            result = PriceUpdateResult()
            outcomes: list[SymbolPriceOutcome] = []
            failed: list[str] = []

            symbol_to_indices = side_data[side_name]
            result.total_symbols = len(symbol_to_indices)
            result.price_fetching_time = fetch_time

            for occ, indices in symbol_to_indices.items():
                quote = quotes.get(occ)
                price: float | None = None

                if quote is not None:
                    money = quote.ask_price if price_side == "ask" else quote.bid_price
                    price = float(money.amount)

                success = price is not None
                if not success:
                    logger.warning(f"No {price_side} price available for {occ}")
                    failed.append(occ)

                for idx in indices:
                    raw_symbol = str(df.loc[idx, col])   # noqa type: ignore[arg-type]
                    outcomes.append(
                        SymbolPriceOutcome(symbol=raw_symbol, price=price, success=success)
                    )

            result.failed = failed
            result.total_time = time.monotonic() - t0
            results[side_name] = (result, outcomes)

            if result.total_symbols:
                logger.info(
                    f"[{side_name}] {result.updated_symbols}/{result.total_symbols} "
                    f"updated in {result.total_time:.1f}s"
                )

        return results