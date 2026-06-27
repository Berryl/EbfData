import pandas as pd

from ebf_data.excel.excel_book_finder import find_open_book
from ebf_data.xlTableBase import xlTable
from ebf_core.guards import guards as g

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
        - If id_val = 123 → return trades with that ID
        """
        g.ensure_str_is_valued(symbol, "symbol")

        df = self.df

        result = df[df["Symbol"] == symbol]

        if id_val is not None:
            result = result[result["ID"] == id_val]

        if len(result) == 0:
            if id_val is None:
                msg = f"No trades found for symbol '{symbol}'"
            else:
                msg = f"No trade found for Symbol='{symbol}', ID={id_val}"
            g.ensure_not_none(None, msg)

        return result