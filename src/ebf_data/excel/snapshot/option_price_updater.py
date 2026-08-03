"""
Option price fetcher for snapshot positions.
"""
import logging
import time

from ebf_trading.domain.value_objects.option_specific.option import Option
from ebf_trading.domain.value_objects.option_specific.symbol_conversion import symbol_converter as sc

from ebf_data.excel.pricing.option_price_fetcher import OptionPriceFetcher
from ebf_data.excel.pricing.price_fetcher import PriceUpdateResult, SymbolPriceOutcome
from ebf_data.excel.pricing.yfinance_option_fetcher import YFinanceOptionFetcher
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

logger = logging.getLogger(__name__)


class OptionPriceUpdater:
    """
    Fetches current option ask prices for short call and short put rows
    using the injected OptionPriceFetcher. Returns per-row outcomes for
    PriceExporter to write to JSON - does not touch the workbook itself.
    """

    SC_SYMBOL_COLUMN = SnapshotTable.SC_SYMBOL_COLUMN
    SC_ASK_COLUMN = SnapshotTable.SC_ASK_COLUMN

    SP_SYMBOL_COLUMN = SnapshotTable.SP_SYMBOL_COLUMN
    SP_ASK_COLUMN = SnapshotTable.SP_ASK_COLUMN

    LC_SYMBOL_COLUMN = SnapshotTable.LC_SYMBOL_COLUMN
    LC_BID_COLUMN = SnapshotTable.LC_BID_COLUMN

    LP_SYMBOL_COLUMN = SnapshotTable.LP_SYMBOL_COLUMN
    LP_BID_COLUMN = SnapshotTable.LP_BID_COLUMN

    def __init__(self, snapshot: SnapshotTable, fetcher: OptionPriceFetcher | None = None,) -> None:
        self._snapshot = snapshot
        self._fetcher = fetcher or YFinanceOptionFetcher()

    def fetch_short_call_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        """Fetch current ask prices for all active short call rows."""
        return self._fetch_short_option_prices(symbol_column=self.SC_SYMBOL_COLUMN)

    def fetch_short_put_prices(self) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        """Fetch current ask prices for all active short put rows."""
        return self._fetch_short_option_prices(symbol_column=self.SP_SYMBOL_COLUMN)

    def _fetch_short_option_prices(self, symbol_column: str, ) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
        """
        Fetch current ask prices for all active short option rows of a
        given type, determined from the symbol column name.
        """
        t0 = time.monotonic()
        result = PriceUpdateResult()

        self._snapshot.refresh()
        df = self._snapshot.df

        active_rows = df[df[symbol_column].notna() & (df[symbol_column] != "")]
        if active_rows.empty:
            logger.info(f"No active rows found for {symbol_column}")
            result.total_time = time.monotonic() - t0
            return result, []

        symbol_to_indices: dict[str, list[int]] = {}
        occ_to_contract: dict[str, Option] = {}
        for idx, row in active_rows.iterrows():
            occ = str(row[symbol_column]).strip()
            try:
                contract = sc.to_option(occ)
            except ValueError as e:
                logger.warning(f"Skipping unparseable OCC symbol {occ!r}: {e}")
                continue
            occ_to_contract[occ] = contract
            symbol_to_indices.setdefault(occ, []).append(idx)

        if not occ_to_contract:
            logger.info(f"No parseable symbols found for {symbol_column}")
            result.total_time = time.monotonic() - t0
            return result, []

        contracts = list(occ_to_contract.values())
        result.total_symbols = len(contracts)
        logger.info(f"Fetching ask prices for {result.total_symbols} contract(s) [{symbol_column}]")

        t1 = time.monotonic()
        prices = self._fetcher.fetch_ask_prices(contracts)
        result.price_fetching_time = time.monotonic() - t1

        failed_symbols: list[str] = []
        outcomes: list[SymbolPriceOutcome] = []

        for occ, indices in symbol_to_indices.items():
            price = prices.get(occ)
            success = price is not None
            if not success:
                logger.warning(f"No ask price available for {occ}")
                failed_symbols.append(occ)
            for idx in indices:
                raw_symbol = str(df.loc[idx, symbol_column])  # noqa type: ignore[arg-type]
                outcomes.append(SymbolPriceOutcome(symbol=raw_symbol, price=price, success=success))

        result.failed = failed_symbols
        result.total_time = time.monotonic() - t0

        logger.info(
            f"Fetched ask prices for {len(contracts) - len(failed_symbols)} of "
            f"{len(contracts)} contract(s) in {result.total_time:.1f}s"
        )

        return result, outcomes