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

AskOrBid = Literal["ask", "bid"]


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

    # region Public API
    def fetch_short_call_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        """Ask prices for active short call rows."""
        return self._fetch_option_prices(self.SC_SYMBOL_COLUMN, side="ask")

    def fetch_short_put_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        """Ask prices for active short-put rows."""
        return self._fetch_option_prices(self.SP_SYMBOL_COLUMN, side="ask")

    def fetch_long_call_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        """Bid prices for active long call rows."""
        return self._fetch_option_prices(self.LC_SYMBOL_COLUMN, side="bid")

    def fetch_long_put_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        """Bid prices for active long put rows."""
        return self._fetch_option_prices(self.LP_SYMBOL_COLUMN, side="bid")

    # endregion

    # region Internal
    def _fetch_option_prices(
            self, symbol_column: str, *, side: AskOrBid
    ) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        t0 = time.monotonic()
        result = PriceUpdateResult()

        self._snapshot.refresh()
        df = self._snapshot.df

        active_rows = df[df[symbol_column].notna() & (df[symbol_column] != "")]
        if active_rows.empty:
            logger.info(f"No active rows found for {symbol_column}")
            result.total_time = time.monotonic() - t0
            return result, []

        # Collect unique OCC symbols and the rows that use them
        symbol_to_indices: dict[str, list[int]] = {}
        valid_symbols: list[str] = []

        for idx, row in active_rows.iterrows():
            occ = str(row[symbol_column]).strip()
            try:
                sc.to_option(occ)  # validate only
            except ValueError as e:
                logger.warning(f"Skipping unparseable OCC symbol {occ!r}: {e}")
                continue

            if occ not in symbol_to_indices:
                valid_symbols.append(occ)
            symbol_to_indices.setdefault(occ, []).append(idx)

        if not valid_symbols:
            logger.info(f"No parseable symbols found for {symbol_column}")
            result.total_time = time.monotonic() - t0
            return result, []

        result.total_symbols = len(valid_symbols)
        logger.info(f"Fetching {side} prices for {result.total_symbols} contract(s) [{symbol_column}]")

        t1 = time.monotonic()
        quotes = self._fetcher.fetch_quotes(valid_symbols)  # ← one call, full quotes
        result.price_fetching_time = time.monotonic() - t1

        failed_symbols: list[str] = []
        outcomes: list[SymbolPriceOutcome] = []

        for occ, indices in symbol_to_indices.items():
            quote = quotes.get(occ)
            price: float | None = None

            if quote is not None:
                money = quote.ask_price if side == "ask" else quote.bid_price
                price = float(money.amount)

            success = price is not None
            if not success:
                logger.warning(f"No {side} price available for {occ}")
                failed_symbols.append(occ)

            for idx in indices:
                raw_symbol = str(df.loc[idx, symbol_column])  # noqa type: ignore[arg-type]
                outcomes.append(
                    SymbolPriceOutcome(symbol=raw_symbol, price=price, success=success)
                )

        result.failed = failed_symbols
        result.total_time = time.monotonic() - t0

        logger.info(
            f"Fetched {side} prices for {len(valid_symbols) - len(failed_symbols)} of "
            f"{len(valid_symbols)} contract(s) in {result.total_time:.1f}s"
        )

        return result, outcomes
    # endregion
