"""
Price updater for snapshot positions.
"""
import logging
import time
from datetime import datetime
from enum import StrEnum, auto

import pandas as pd
from ebf_core.date_time.formatting import get_formatted_datetime, get_formatted_time_no_tz

from ebf_data.excel.infrastructure.suspend_app_updates import SuspendAppUpdates
from ebf_data.excel.infrastructure.table_helpers import get_data_body_column
from ebf_data.excel.pricing.price_fetcher import PriceFetcher, PriceUpdateResult
from ebf_data.excel.pricing.yfinance_fetcher import YFinanceFetcher
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

logger = logging.getLogger(__name__)

_XL_VALIDATE_INPUT_ONLY = 0


class PriceUpdateScope(StrEnum):
    ALL = auto()  # all active positions (as determined by the Position being non-blank)
    SELECTED = auto()  # rows intersecting the current Excel selection & Symbol column
    VISIBLE = auto()  # rows not hidden by an active filter


# region helpers
def _extract_base_symbol(snapshot_symbol: str) -> str:
    """
    Some symbols may have non-standard suffixes (e.g., CCJ_17, MARA_4.1).
    """
    return snapshot_symbol.split("_")[0]


def _set_dv_message(rng, title: str, message: str) -> None:
    """
    Set a Data Validation input message on a range without constraining
    the cell value (xlValidateInputOnly). Clears any existing DV first.
    """
    try:
        rng.api.Validation.Delete()
        rng.api.Validation.Add(
            Type=_XL_VALIDATE_INPUT_ONLY,
            AlertStyle=1,
            Operator=1,
            Formula1="0",
        )
        rng.api.Validation.InputTitle = title
        rng.api.Validation.InputMessage = message
        rng.api.Validation.ShowInput = True
    except Exception as e:
        logger.warning(f"Could not set DV message on range: {e}")


# endregion


class PriceUpdater:
    """
    Writes current market prices into the Last Price column using the injected PriceFetcher.
    The scope parameter controls which rows (Symbols) are targeted. See PriceUpdateScope
    """

    SYMBOL_COLUMN = "Symbol"
    LAST_PRICE_COLUMN = "Last Price"
    POSITION_COLUMN = "Position"
    RUN_INFO_RANGE = "LastPriceRunInfo"
    DV_TITLE = "YFinance Pricing"

    def __init__(self, snapshot: SnapshotTable, fetcher: PriceFetcher | None = None) -> None:
        self._snapshot = snapshot
        self._fetcher = fetcher or YFinanceFetcher()

    def update_prices(self, scope: PriceUpdateScope = PriceUpdateScope.ALL) -> PriceUpdateResult:
        """
        Fetch and write current prices for snapshot rows in the given scope.
        """
        t0 = time.monotonic()
        result = PriceUpdateResult()

        self._snapshot.refresh()
        df = self._snapshot.df

        target = self._get_rows(df, scope)
        if target.empty:
            logger.info(f"No rows to update for scope={scope}")
            result.total_time = time.monotonic() - t0
            return result

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

        t2 = time.monotonic()
        data_body = self._snapshot.table.data_body_range
        table_row_count = data_body.shape[0]
        last_price_col_index = df.columns.get_loc(self.LAST_PRICE_COLUMN)
        last_price_ws_col = get_data_body_column(data_body, df, self.LAST_PRICE_COLUMN)

        # Read the full Last Price column once
        first_row = data_body.row
        target_range = self._snapshot.sheet.range(
            (first_row, last_price_ws_col),
            (first_row + table_row_count - 1, last_price_ws_col)
        )
        last_price_values: list = target_range.value

        for ticker, indices in ticker_to_indices.items():
            price = prices.get(ticker)
            if price is None:
                logger.warning(f"No price available for {ticker} - Last Price unchanged")
                failed_tickers.append(ticker)
                self._flag_failed_rows(ticker, indices)
                continue
            for idx in indices:
                row_position: int = df.index.get_loc(idx)
                if row_position >= table_row_count:
                    logger.warning(
                        f"Skipping write for {ticker} at position {row_position} "
                        f"- outside data body range"
                    )
                    continue
                last_price_values[row_position] = price
                result.updated_rows += 1

        with SuspendAppUpdates(self._snapshot.book.app):
            target_range.value = [[v] for v in last_price_values]

        result.excel_updating_time = time.monotonic() - t2
        result.failed = failed_tickers

        self._summarize_run(result, scope)
        result.total_time = time.monotonic() - t0

        return result

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

    def _flag_failed_rows(self, ticker: str, indices: list[int]) -> None:
        """Set a DV error message on each Last Price cell for a failed ticker."""
        col_index = self._snapshot.df.columns.get_loc(self.LAST_PRICE_COLUMN)
        table_row_count = self._snapshot.table.data_body_range.shape[0]
        for idx in indices:
            row_position: int = self._snapshot.df.index.get_loc(idx)
            if row_position >= table_row_count:
                logger.warning(
                    f"Skipping DV flag for {ticker} at position {row_position} "
                    f"- outside table data body range ({table_row_count} rows)"
                )
                continue
            cell = self._snapshot.table.data_body_range[row_position, col_index]
            _set_dv_message(cell, self.DV_TITLE, f"⚠ No price available for {ticker}")

    def _summarize_run(self, result: PriceUpdateResult, scope: PriceUpdateScope, ) -> None:
        try:
            run_info_range = self._snapshot.book.names[self.RUN_INFO_RANGE].refers_to_range
            timestamp = get_formatted_datetime(datetime.now(), time_fmt=get_formatted_time_no_tz, )
            message = (
                f"updated {result.updated_rows} rows across "
                f"{result.updated_symbols} of {result.total_symbols} symbols "
                f"[{scope}]\n{timestamp}"
            )
            if result.failed:
                message += f"\nFailed: {', '.join(result.failed)}"

            _set_dv_message(run_info_range, self.DV_TITLE, message)

            logger.info(
                f"Updated Last Price for {result.updated_rows} row(s) across "
                f"{result.updated_symbols} of {result.total_symbols} symbol(s) "
                f"in {result.total_time:.1f}s"
            )

        except Exception as e:
            logger.warning(
                f"Could not write run summary to {self.RUN_INFO_RANGE}: {e}"
            )
