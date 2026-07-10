from datetime import datetime

import pandas as pd
from ebf_core.guards import guards as g
from ebf_trading.domain.entities.transaction_events.transaction_event_type import TransactionEventType

from ebf_data.excel.infrastructure.excel_book_finder import find_open_book
from ebf_data.excel.infrastructure.xl_table_base import xlTable

CAGR_WB = "CAGR.xlsm"
CAGR_WKS = "CAGR"
CAGR_TABLE = "CagrTable"
ACB = "TacticalAcb"  # defined name


class CagrTable(xlTable):
    def __init__(self) -> None:
        super().__init__(find_open_book(CAGR_WB), CAGR_WKS, CAGR_TABLE)

    def get_trade(self, symbol: str, id_val: int | None = None) -> pd.DataFrame:
        """
        Find trade(s) by Symbol.
        - If id_val is None → return ALL trades for that Symbol
        - If id_val = 3 → return trades with that ID
        """
        g.ensure_str_is_valued(symbol, "symbol")

        df = self.df

        result = df[df["Symbol"] == symbol]

        if id_val is not None:
            g.ensure_positive_number(id_val, description="id_val")
            result = result[result["ID"] == id_val]

        self._ensure_symbol_exists(result, symbol, id_val)
        return result

    def max_id_for_symbol(self, symbol: str) -> int:
        """Return the highest trade ID for the passed Symbol."""
        g.ensure_str_is_valued(symbol, "symbol")

        df = self.df
        symbol_trades = df[df["Symbol"] == symbol]

        self._ensure_symbol_exists(symbol_trades, symbol)
        return int(symbol_trades["ID"].max())

    def close_trade_leg(self,
                        row: pd.DataFrame,
                        event: TransactionEventType,
                        underlying_price: float | int,
                        exit_fill_time: datetime) -> None:
        """
        Close out a single open trade leg in CAGR.
        """
        g.ensure_true(len(row) == 1, f"closing trade row must contain exactly one row, got {len(row)}")

        index_label = row.index[0]

        self.update_row(index_label, {
            "Is Closed": "Y",
            "Exit Trigger": "OPEX",
            "Exit Und Price": underlying_price,
            "Exit Fill Time": exit_fill_time,
            "Exit Trade": event.value.capitalize(),
        })

    @staticmethod
    def _ensure_symbol_exists(df: pd.DataFrame, symbol: str, id_val: int | None = None):
        if len(df) == 0:
            msg = f"No trades found for symbol '{symbol}'"
            if id_val is not None:
                msg += f" with ID={id_val}"
            g.ensure_not_none(None, msg)

    # region masks
    @staticmethod
    def is_closed(df: pd.DataFrame) -> pd.Series:
        """True if 'Is Closed' column == 'Y'"""
        if df.empty:
            return pd.Series([], dtype=bool, index=df.index)
        return df['Is Closed'] == "Y"

    @staticmethod
    def is_open(df: pd.DataFrame) -> pd.Series:
        """True if trade is Open (opposite of is_closed)"""
        if df.empty:
            return pd.Series([], dtype=bool, index=df.index)
        return ~CagrTable.is_closed(df)

    # endregion

    # region filters
    @staticmethod
    def by_position(df: pd.DataFrame, position: str) -> pd.DataFrame:
        """
        Filter the given DataFrame to rows with the specified Position.
        """
        if df.empty:
            return df
        return df[df['Position'] == position]

    def open_legs(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return only open legs from the given DataFrame"""
        if df.empty:
            return df
        return df[self.is_open(df)]

    def closed_legs(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return only closed legs from the given DataFrame"""
        if df.empty:
            return df
        return df[self.is_closed(df)]

    # endregion

    # region chaining (with pipe)
    def where_closed(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return only closed legs (convenience alias for closed_legs)"""
        return self.closed_legs(df)

    def where_open(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return only open legs (convenience alias for open_legs)"""
        return self.open_legs(df)
    # endregion