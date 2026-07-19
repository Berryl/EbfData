# option_price_updater.py
"""
Option price updater for snapshot positions.

Reads active option rows from SnapshotTable, fetches current ask prices
via an injected OptionPriceFetcher, and writes them back to the
appropriate Current Ask column.

"""
import logging
import time
from datetime import datetime

from ebf_core.date_time.formatting import get_formatted_datetime, get_formatted_time_no_tz
from ebf_trading.domain.value_objects.option_specific.option import Option
from ebf_trading.domain.value_objects.option_specific.symbol_conversion import symbol_converter as sc

from ebf_data.excel.infrastructure.suspend_app_updates import SuspendAppUpdates
from ebf_data.excel.infrastructure.table_helpers import get_data_body_column
from ebf_data.excel.pricing.option_price_fetcher import OptionPriceFetcher
from ebf_data.excel.pricing.price_fetcher import PriceUpdateResult
from ebf_data.excel.pricing.yfinance_option_fetcher import YFinanceOptionFetcher
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable
from ebf_data.excel.snapshot.price_updater import _set_dv_message

logger = logging.getLogger(__name__)

_XL_VALIDATE_INPUT_ONLY = 0


class OptionPriceUpdater:
    """
    Writes current option ask prices into the appropriate Current Ask
    column using the injected OptionPriceFetcher.
    """

    SC_SYMBOL_COLUMN = "SC Symbol"
    SC_ASK_COLUMN = "SC Current Ask"
    SC_RUN_INFO_RANGE = "LastShortCallUpdateInfo"
    DV_TITLE = "YFinance Option Pricing"

    def __init__(
        self,
        snapshot: SnapshotTable,
        fetcher: OptionPriceFetcher | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._fetcher = fetcher or YFinanceOptionFetcher()

    def update_short_call_prices(self) -> PriceUpdateResult:
        """
        Fetch and write current ask prices for all active short call rows.
        """
        t0 = time.monotonic()
        result = PriceUpdateResult()

        self._snapshot.refresh()
        df = self._snapshot.df

        sc_rows = df[df[self.SC_SYMBOL_COLUMN].notna() & (df[self.SC_SYMBOL_COLUMN] != "")]
        if sc_rows.empty:
            logger.info("No active short call rows found")
            result.total_time = time.monotonic() - t0
            return result

        # Convert OCC symbols to Option domain objects; skip unparseable symbols
        symbol_to_indices: dict[str, list[int]] = {}
        occ_to_contract: dict[str, Option] = {}
        for idx, row in sc_rows.iterrows():
            occ = str(row[self.SC_SYMBOL_COLUMN]).strip()
            try:
                contract = sc.to_option(occ)
                occ_to_contract[occ] = contract
                symbol_to_indices.setdefault(occ, []).append(idx)
            except ValueError as e:
                logger.warning(f"Skipping unparseable OCC symbol {occ!r}: {e}")

        if not occ_to_contract:
            logger.info("No parseable short call symbols found")
            result.total_time = time.monotonic() - t0
            return result

        contracts = list(occ_to_contract.values())
        result.total_symbols = len(contracts)
        logger.info(f"Fetching ask prices for {result.total_symbols} short call contract(s)")

        t1 = time.monotonic()
        prices = self._fetcher.fetch_ask_prices(contracts)
        result.price_fetching_time = time.monotonic() - t1

        failed_symbols: list[str] = []

        t2 = time.monotonic()
        data_body = self._snapshot.table.data_body_range
        table_row_count = data_body.shape[0]
        sc_ask_ws_col = get_data_body_column(data_body, df, self.SC_ASK_COLUMN)
        first_row = data_body.row

        sc_ask_range = self._snapshot.sheet.range(
            (first_row, sc_ask_ws_col),
            (first_row + table_row_count - 1, sc_ask_ws_col)
        )
        sc_ask_values: list = sc_ask_range.value

        for occ, indices in symbol_to_indices.items():
            ask = prices.get(occ)
            if ask is None:
                logger.warning(f"No ask price available for {occ} - SC Current Ask unchanged")
                failed_symbols.append(occ)
                continue
            for idx in indices:
                row_position: int = df.index.get_loc(idx)
                if row_position >= table_row_count:
                    logger.warning(
                        f"Skipping write for {occ} at position {row_position} "
                        f"- outside data body range"
                    )
                    continue
                sc_ask_values[row_position] = ask
                result.updated_rows += 1

        with SuspendAppUpdates(self._snapshot.book.app):
            sc_ask_range.value = [[v] for v in sc_ask_values]

        result.excel_updating_time = time.monotonic() - t2
        result.failed = failed_symbols

        self._summarize_run(result)
        result.total_time = time.monotonic() - t0

        return result
    def _summarize_run(self, result: PriceUpdateResult) -> None:
        try:
            run_info_range = self._snapshot.book.names[self.SC_RUN_INFO_RANGE].refers_to_range
            timestamp = get_formatted_datetime(datetime.now(), time_fmt=get_formatted_time_no_tz)
            message = (
                f"updated {result.updated_rows} rows across "
                f"{result.updated_symbols} of {result.total_symbols} contracts\n"
                f"{timestamp}"
            )
            if result.failed:
                message += f"\nFailed: {', '.join(result.failed)}"
            _set_dv_message(run_info_range, self.DV_TITLE, message)
            logger.info(
                f"Updated SC Current Ask for {result.updated_rows} row(s) across "
                f"{result.updated_symbols} of {result.total_symbols} contract(s) "
                f"in {result.total_time:.1f}s"
            )
        except Exception as e:
            logger.warning(f"Could not write run summary to {self.SC_RUN_INFO_RANGE}: {e}")