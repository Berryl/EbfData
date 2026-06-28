import pandas as pd
from ebf_core.guards import guards as g

from ebf_data.excel.excel_book_finder import find_open_book
from ebf_data.xlTableBase import xlTable

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
            result = result[result["ID"] == id_val]

        if len(result) == 0:
            msg = f"No trades found for symbol '{symbol}'"
            if id_val is not None:
                msg = msg + f" with ID={id_val}"
            g.ensure_not_none(None, msg)

        return result

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