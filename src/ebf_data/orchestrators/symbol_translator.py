from ebf_core.guards import guards as g

from ebf_data.excel.cagr.cagr_table import CagrTable


class SymbolTranslator:
    def __init__(self, cagr: CagrTable) -> None:
        g.ensure_not_none(cagr, "cagr")

        self._cagr = cagr

    def to_cagr_values(self, snapshot_symbol: str) -> tuple[str, int, bool]:
        """
        Convert snapshot symbol to (cagr_symbol, id_val, has_tranches)

        Examples:
            "YUM"      -> ("YUM", 1, False)
            "FCX_20"   -> ("FCX", 20, False)
            "MARA_4.2" -> ("MARA", 4, True)
        """
        g.ensure_str_is_valued(snapshot_symbol, "snapshot_symbol")

        if "_" not in snapshot_symbol:
            # No suffix → use max ID from CAGR
            symbol = snapshot_symbol
            id_val = self._cagr.max_id_for_symbol(symbol)
            has_tranches = False
        else:
            # Has suffix like "FCX_20" or "MARA_4.2"
            symbol, suffix = snapshot_symbol.split("_", 1)

            if "." in suffix:
                # Tranches like "4.2"
                id_part, _ = suffix.split(".", 1)
                id_val = int(id_part)
                has_tranches = True
            else:
                # Simple suffix like "20"
                id_val = int(suffix)
                has_tranches = False

        return symbol, id_val, has_tranches