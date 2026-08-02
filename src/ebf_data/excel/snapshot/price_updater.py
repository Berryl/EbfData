"""
Price fetcher for snapshot positions.

"""
import logging
import time
from dataclasses import dataclass
from enum import StrEnum, auto

import pandas as pd

from ebf_data.excel.infrastructure.table_helpers import get_data_body_column
from ebf_data.excel.pricing.price_fetcher import PriceFetcher, PriceUpdateResult
from ebf_data.excel.pricing.yfinance_fetcher import YFinanceFetcher
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

logger = logging.getLogger(__name__)


class PriceUpdateScope(StrEnum):
    ALL = auto()  # all active positions (as determined by the Position being non-blank)
    SELECTED = auto()  # rows intersecting the current Excel selection & Symbol column
    VISIBLE = auto()  # rows not hidden by an active filter


@dataclass(frozen=True)
class SymbolPriceOutcome:
    """
    One row's fetch outcome: the raw Symbol-column text, the fetched price
    (None on failure), and whether the fetch succeeded.

    Kept separate from PriceUpdateResult (aggregate run stats). A
    workbook can have duplicate or suffixed symbols (e.g., two "PLTR" rows,
    or "CCJ_17" / "CCJ_4.1" sharing a single fetch against base ticker
    "CCJ"), and each will need their own JSON entry carrying the raw text VBA
    will match against the Symbol column.
    """
    symbol: str
    price: float | None
    success: bool


# region helpers
def _extract_base_symbol(snapshot_symbol: str) -> str:
    """
    Some symbols may have non-standard suffixes (e.g., CCJ_17, MARA_4.1).
    """
    return snapshot_symbol.split("_")[0]


# endregion


class PriceUpdater:
    """
    Fetches current market prices for a scope of snapshot rows using the
    injected PriceFetcher. Returns per-row outcomes for PriceExporter to
    write to JSON - does not touch the workbook itself. See PriceUpdateScope
    for how the row scope is determined.
    """

    SYMBOL_COLUMN = SnapshotTable.SYMBOL_COLUMN
    POSITION_COLUMN = SnapshotTable.POSITION_COLUMN

    def __init__(self, snapshot: SnapshotTable, fetcher: PriceFetcher | None = None) -> None:
        self._snapshot = snapshot
        self._fetcher = fetcher or YFinanceFetcher()

    def fetch_prices(self, scope: PriceUpdateScope = PriceUpdateScope.ALL) -> tuple[
        PriceUpdateResult, list[SymbolPriceOutcome]]:
        """
        Fetch current prices for snapshot rows in the given scope.

        Returns the aggregate run summary alongside one SymbolPriceOutcome
        per targeted row, in the raw Symbol-column text (duplicates and
        suffixed variants included, each carrying the price fetched for
        their shared base ticker).
        """
        t0 = time.monotonic()
        result = PriceUpdateResult()

        self._snapshot.refresh()
        df = self._snapshot.df

        target = self._get_rows(df, scope)
        if target.empty:
            logger.info(f"No rows to update for scope={scope}")
            result.total_time = time.monotonic() - t0
            return result, []

        ticker_to_indices: dict[str, list[int]] = {}
        for idx, row in target.iterrows():
            ticker = _extract_base_symbol(str(row[self.SYMBOL_COLUMN]))
            ticker_to_indices.setdefault(ticker, []).append(idx)

        tickers = list(ticker_to_indices.keys())
        result.total_symbols = len(tickers)
        logger.info(f"Fetching prices for {len(tickers)} symbol(s) [{scope}]: {tickers}")

        t1 = time.monotonic()
        prices = self._fetcher.fetch_prices(tickers)
        result.price_fetching_time = time.monotonic() - t1

        failed_tickers: list[str] = []
        outcomes: list[SymbolPriceOutcome] = []

        for ticker, indices in ticker_to_indices.items():
            price = prices.get(ticker)
            success = price is not None
            if not success:
                logger.warning(f"No price available for {ticker}")
                failed_tickers.append(ticker)
            for idx in indices:
                raw_symbol = str(df.loc[idx, self.SYMBOL_COLUMN])  # noqa type: ignore[arg-type]
                outcomes.append(SymbolPriceOutcome(symbol=raw_symbol, price=price, success=success))

        result.failed = failed_tickers
        result.total_time = time.monotonic() - t0

        logger.info(
            f"Fetched prices for {len(tickers) - len(failed_tickers)} of "
            f"{len(tickers)} symbol(s) in {result.total_time:.1f}s"
        )

        return result, outcomes

    def _get_rows(self, df: pd.DataFrame, scope: PriceUpdateScope) -> pd.DataFrame:
        """Return the subset of df rows to update for the given scope."""
        if scope == PriceUpdateScope.ALL:
            return self._get_all_rows(df)

        if scope == PriceUpdateScope.SELECTED:
            return self._get_selected_rows(df)

        if scope == PriceUpdateScope.VISIBLE:
            return self._get_visible_rows(df)

        return df.iloc[0:0]  # empty - unknown scope

    def _get_all_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return rows with non-blank Position."""
        return df[df[self.POSITION_COLUMN].notna() & (df[self.POSITION_COLUMN] != "")]

    def _get_selected_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Return rows whose position in the table intersects the current
        Excel selection. Uses Application.Intersect against the Symbol
        column to find matching rows regardless of which column is active.
        """
        try:
            symbol_col_range = self._snapshot.table.data_body_range.columns[
                df.columns.get_loc(self.SYMBOL_COLUMN)
            ]
            selection = self._snapshot.sheet.api.Application.Selection
            intersection = self._snapshot.sheet.api.Application.Intersect(
                symbol_col_range.api, selection
            )
            if intersection is None:
                logger.info("Selection does not intersect the Symbol column")
                return df.iloc[0:0]

            # Collect DataFrame positional indices from the intersected rows
            table_start_row = self._snapshot.table.data_body_range.row
            selected_positions = []
            for area in intersection.Areas:
                for r in range(area.Row, area.Row + area.Rows.Count):
                    position = r - table_start_row
                    if 0 <= position < len(df):
                        selected_positions.append(position)

            return df.iloc[selected_positions]

        except Exception as e:
            logger.error(f"Could not determine selection - falling back to ALL: {e}")
            return df[df[self.POSITION_COLUMN].notna() & (df[self.POSITION_COLUMN] != "")]

    def _get_visible_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return rows that are not hidden by an active filter."""
        _XL_CELL_TYPE_VISIBLE = 12

        try:
            symbol_ws_col = get_data_body_column(
                self._snapshot.table.data_body_range, df, self.SYMBOL_COLUMN
            )

            data_body = self._snapshot.table.data_body_range
            first = data_body.row
            last = first + data_body.shape[0] - 1

            symbol_range = self._snapshot.sheet.range(
                (first, symbol_ws_col), (last, symbol_ws_col)
            )

            visible_range = symbol_range.api.SpecialCells(_XL_CELL_TYPE_VISIBLE)

            visible_ws_rows = {
                r
                for area in visible_range.Areas
                for r in range(area.Row, area.Row + area.Rows.Count)
            }

            visible_positions = [
                i for i in range(len(df)) if first + i in visible_ws_rows
            ]
            return df.iloc[visible_positions]

        except Exception:  # noqa: broad-except
            # SpecialCells raises when no rows are visible or no filter is active
            logger.info("No visible rows (or no filter active)")
            return df.iloc[:0]
