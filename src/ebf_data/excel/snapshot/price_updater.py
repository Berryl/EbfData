"""
Price updater for snapshot positions.

Reads active rows from SnapshotTable (where the Position column is non-blank),
extracts unique base symbols, fetches current prices from yFinance
in a single batch call, and writes Last Price back to each row.

Symbols with non-standard suffixes (e.g., CCJ_17, MARA_4.1) are
reduced to their base ticker (everything before the first '_') for
the yFinance fetch, then matched back to all rows sharing that ticker.

Failures per symbol are logged as warnings - Last Price is left
unchanged for any symbol yFinance cannot price.

After each run:
- The named range LastPriceRunInfo receives a DV input message
  summarizing the run (symbol count plus timestamp).
- Any Last Price cell whose symbol failed to price receives its own
  DV input message flagging the specific failure.
"""
import logging
from datetime import datetime

import pandas as pd
import yfinance as yf
from ebf_core.date_time.formatting import get_formatted_datetime

from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

logger = logging.getLogger(__name__)

# xlValidateInputOnly - shows an input message with no value constraint
_XL_VALIDATE_INPUT_ONLY = 0


def _extract_base_symbol(snapshot_symbol: str) -> str:
    """
    Examples:
        'BA'      -> 'BA'
        'CCJ_17'  -> 'CCJ'
        'MARA_4.1'-> 'MARA'
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


class PriceUpdater:
    """
    Fetches current market prices from yFinance and writes them back
    to the Last Price column of a SnapshotTable.

    Only updates rows where Position is non-blank (active positions).
    Leaves Last Price unchanged for any symbol that cannot be priced
    and logs a warning for each failure.

    After each run, writes a summary DV message to the named range
    LastPriceRunInfo, and per-cell DV messages on any Last Price cell
    whose symbol failed to price.
    """

    POSITION_COLUMN = "Position"
    SYMBOL_COLUMN = "Symbol"
    LAST_PRICE_COLUMN = "Last Price"
    RUN_INFO_RANGE = "LastPriceRunInfo"
    DV_TITLE = "YFinance Pricing"

    def __init__(self, snapshot: SnapshotTable) -> None:
        self._snapshot = snapshot

    def update_prices(self) -> None:
        """
        Fetch and write current prices for all active snapshot positions.

        Active = Position column is non-blank. Processes all active rows
        in a single yFinance batch call for efficiency.
        """
        self._snapshot.refresh()
        df = self._snapshot.df

        active = df[df[self.POSITION_COLUMN].notna() & (df[self.POSITION_COLUMN] != "")]
        if active.empty:
            logger.info("No active positions found - nothing to update")
            return

        # Map base ticker -> list of DataFrame index labels that share it
        ticker_to_indices: dict[str, list] = {}
        for idx, row in active.iterrows():
            ticker = _extract_base_symbol(str(row[self.SYMBOL_COLUMN]))
            ticker_to_indices.setdefault(ticker, []).append(idx)

        tickers = list(ticker_to_indices.keys())
        logger.info(f"Fetching prices for {len(tickers)} symbol(s): {tickers}")

        prices = self._fetch_prices(tickers)

        updated = 0
        failed_tickers: list[str] = []

        for ticker, indices in ticker_to_indices.items():
            price = prices.get(ticker)
            if price is None:
                logger.warning(f"No price available for {ticker} - Last Price unchanged")
                failed_tickers.append(ticker)
                self._flag_failed_rows(ticker, indices)
                continue
            for idx in indices:
                self._snapshot.update_row(idx, {self.LAST_PRICE_COLUMN: price})
                updated += 1

        self._write_run_summary(updated, len(tickers), failed_tickers)
        logger.info(f"Updated Last Price for {updated} row(s)")

    def _flag_failed_rows(self, ticker: str, indices: list) -> None:
        """Set a DV error message on each Last Price cell for a failed ticker."""
        col_index = self._snapshot.df.columns.get_loc(self.LAST_PRICE_COLUMN)
        for idx in indices:
            row_position = self._snapshot.df.index.get_loc(idx)
            cell = self._snapshot.table.data_body_range[row_position, col_index]
            _set_dv_message(cell, self.DV_TITLE, f"⚠ No price available for {ticker}")

    def _write_run_summary(self, updated: int, total: int, failed: list[str]) -> None:
        """Write a run summary DV message to the LastPriceRunInfo named range."""
        try:
            run_info_range = self._snapshot.book.names[self.RUN_INFO_RANGE].refers_to_range

            timestamp = get_formatted_datetime(datetime.now())

            message = f"updated {updated} of {total} symbols\n{timestamp}"
            if failed:
                message += f"\nFailed: {', '.join(failed)}"

            _set_dv_message(run_info_range, self.DV_TITLE, message)
        except Exception as e:
            logger.warning(f"Could not write run summary to {self.RUN_INFO_RANGE}: {e}")

    @staticmethod
    def _fetch_prices(tickers: list[str]) -> dict[str, float | None]:
        """
        Fetch the most recent price for each ticker via yFinance.

        Primary method: yf.Tickers.info (best for current/last price)
        Fallback: yf.download with group_by='ticker' for consistency.
        Returns dict mapping ticker -> price (float) or None if unavailable.
        """
        if not tickers:
            return {}

        prices: dict[str, float | None] = {}
        failed: list[str] = []

        # === PRIMARY METHOD: yf.Tickers.info ===
        try:
            yftickers = yf.Tickers(" ".join(tickers))
            for ticker in tickers:
                try:
                    info = yftickers.tickers[ticker].info
                    # Best fields for current/last traded price
                    price = (
                        info.get("currentPrice")
                        or info.get("regularMarketPrice")
                        or info.get("previousClose")
                    )
                    prices[ticker] = float(price) if price is not None else None
                except Exception as e:
                    logger.warning(f"Could not get price info for {ticker}: {e}")
                    prices[ticker] = None
                    failed.append(ticker)

        except Exception as e:
            logger.warning(f"yFinance Tickers failed ({e}), falling back to download...")

            # === FALLBACK: yf.download() ===
            try:
                data: pd.DataFrame = yf.download(
                    tickers=tickers,
                    period="1d",
                    interval="1m",
                    group_by="ticker",
                    auto_adjust=True,
                    prepost=True,           # include after-hours data if available
                    progress=False,
                    threads=True,
                )

                for ticker in tickers:
                    try:
                        # Handle both single-ticker (flat) and multi-ticker cases
                        if len(tickers) == 1 and not isinstance(data.columns, pd.MultiIndex):
                            close_series = data["Close"]
                        else:
                            close_series = data[ticker]["Close"]

                        close = close_series.dropna()
                        prices[ticker] = float(close.iloc[-1]) if not close.empty else None

                    except Exception as inner_e:
                        logger.warning(f"Could not extract price for {ticker}: {inner_e}")
                        prices[ticker] = None
                        failed.append(ticker)

            except Exception as download_e:
                logger.error(f"yFinance download fallback also failed: {download_e}")
                prices = {t: None for t in tickers}

        if failed:
            logger.warning(f"Failed to fetch prices for: {', '.join(failed)}")

        return prices