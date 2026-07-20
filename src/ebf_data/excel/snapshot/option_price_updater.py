"""
Option price updater for snapshot positions.
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

    SP_SYMBOL_COLUMN = "SP Symbol"
    SP_ASK_COLUMN = "SP Current Ask"
    SP_RUN_INFO_RANGE = "LastShortPutUpdateInfo"

    DV_TITLE = "YFinance Option Pricing"

    def __init__(
        self,
        snapshot: SnapshotTable,
        fetcher: OptionPriceFetcher | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._fetcher = fetcher or YFinanceOptionFetcher()

    def update_short_call_prices(self) -> PriceUpdateResult:
        """Fetch and write current ask prices for all active short call rows."""
        return self._update_short_option_prices(
            symbol_column=self.SC_SYMBOL_COLUMN,
            ask_column=self.SC_ASK_COLUMN,
            run_info_range=self.SC_RUN_INFO_RANGE,
        )

    def update_short_put_prices(self) -> PriceUpdateResult:
        """Fetch and write current ask prices for all active short put rows."""
        return self._update_short_option_prices(
            symbol_column=self.SP_SYMBOL_COLUMN,
            ask_column=self.SP_ASK_COLUMN,
            run_info_range=self.SP_RUN_INFO_RANGE,
        )

    def _update_short_option_prices(
        self,
        symbol_column: str,
        ask_column: str,
        run_info_range: str,
    ) -> PriceUpdateResult:
        """
        Fetch and write current ask prices for all active short option rows
        of a given type. Driven by the symbol and ask column names, and the
        named range for the run summary DV message.
        """
        t0 = time.monotonic()
        result = PriceUpdateResult()

        self._snapshot.refresh()
        df = self._snapshot.df

        sc_rows = df[df[symbol_column].notna() & (df[symbol_column] != "")]
        if sc_rows.empty:
            logger.info(f"No active rows found for {symbol_column}")
            result.total_time = time.monotonic() - t0
            return result

        symbol_to_indices: dict[str, list[int]] = {}
        occ_to_contract: dict[str, Option] = {}
        for idx, row in sc_rows.iterrows():
            occ = str(row[symbol_column]).strip()
            try:
                contract = sc.to_option(occ)
                occ_to_contract[occ] = contract
                symbol_to_indices.setdefault(occ, []).append(idx)
            except ValueError as e:
                logger.warning(f"Skipping unparseable OCC symbol {occ!r}: {e}")

        if not occ_to_contract:
            logger.info(f"No parseable symbols found for {symbol_column}")
            result.total_time = time.monotonic() - t0
            return result

        contracts = list(occ_to_contract.values())
        result.total_symbols = len(contracts)
        logger.info(f"Fetching ask prices for {result.total_symbols} contract(s) [{symbol_column}]")

        t1 = time.monotonic()
        prices = self._fetcher.fetch_ask_prices(contracts)
        result.price_fetching_time = time.monotonic() - t1

        failed_symbols: list[str] = []

        t2 = time.monotonic()
        data_body = self._snapshot.table.data_body_range
        table_row_count = data_body.shape[0]
        ask_ws_col = get_data_body_column(data_body, df, ask_column)
        first_row = data_body.row

        ask_range = self._snapshot.sheet.range(
            (first_row, ask_ws_col),
            (first_row + table_row_count - 1, ask_ws_col)
        )
        ask_values: list = ask_range.value

        for occ, indices in symbol_to_indices.items():
            ask = prices.get(occ)
            if ask is None:
                logger.warning(f"No ask price available for {occ} - {ask_column} unchanged")
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
                ask_values[row_position] = ask
                result.updated_rows += 1

        with SuspendAppUpdates(self._snapshot.book.app):
            ask_range.value = [[v] for v in ask_values]

        result.excel_updating_time = time.monotonic() - t2
        result.failed = failed_symbols

        self._summarize_run(result, run_info_range)
        result.total_time = time.monotonic() - t0

        return result

    def _summarize_run(self, result: PriceUpdateResult, run_info_range: str) -> None:
        try:
            rng = self._snapshot.book.names[run_info_range].refers_to_range
            timestamp = get_formatted_datetime(datetime.now(), time_fmt=get_formatted_time_no_tz)
            message = (
                f"updated {result.updated_rows} rows across "
                f"{result.updated_symbols} of {result.total_symbols} contracts\n"
                f"{timestamp}"
            )
            if result.failed:
                message += f"\nFailed: {', '.join(result.failed)}"
            _set_dv_message(rng, self.DV_TITLE, message)
            logger.info(
                f"Updated {result.updated_rows} row(s) across "
                f"{result.updated_symbols} of {result.total_symbols} contract(s) "
                f"in {result.total_time:.1f}s"
            )
        except Exception as e:
            logger.warning(f"Could not write run summary to {run_info_range}: {e}")