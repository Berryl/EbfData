from ebf_core.guards import guards as g

from ebf_data.excel.cagr.cagr_table import CagrTable


class SymbolTranslator:
    def __init__(self, cagr: CagrTable) -> None:
        g.ensure_not_none(cagr, "cagr")

        self._cagr = cagr

    def to_cagr_values(self, snapshot_symbol: str) -> tuple[str, int]:
        """

        :param snapshot_symbol:
        :return: a tuple of (symbol, id, has_tranches)

        For example, 'MARA_4.2' implies there is a 'MARA_4.1' and that there were tranches,
        different fill times, prices, expiration dates, etc.
        """
        g.ensure_str_is_valued(snapshot_symbol, "snapshot_symbol")

        symbol = snapshot_symbol
        id_val = -1
        has_tranches = False
        if "_" in snapshot_symbol:
            result = snapshot_symbol.split("_")
            symbol = result[0]
            result = result[1]
            if "." in result:
                result = result.split(".")
                id_val = int(result[0])
                has_tranches = True
            else:
                id_val = int(result)
        else:

            id_val = self._cagr.max_id_for_symbol(symbol)
        return symbol, id_val, has_tranches
