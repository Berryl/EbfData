import pandas as pd
from ebf_core.guards import guards as g

from ebf_data.excel.cagr.cagr_table import CagrTable
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable
from ebf_data.orchestrators.symbol_translator import SymbolTranslator


class OpexProcessor:
    def __init__(self, cagr: CagrTable, snapshot: SnapshotTable) -> None:
        g.ensure_not_none(cagr, "cagr")
        g.ensure_not_none(snapshot, "snapshot")

        self._cagr = cagr
        self._snapshot = snapshot
        self._symbol_translator = SymbolTranslator(cagr)

    def close_out_expired_short_calls(self) -> None:
        to_close = self._snapshot.get_expired_short_calls()

        if to_close.empty:
            print("No expired short calls to close.")
            return

        for _, row in to_close.iterrows():
            snapshot_symbol = row['Symbol']
            symbol, id_val, has_tranches = self._symbol_translator.to_cagr_values(snapshot_symbol)

            # Get open SC trades in CAGR for this symbol
            candidates = self._cagr.get_trade(symbol, id_val)
            candidates = self._cagr.by_position(candidates, "SC").pipe(self._cagr.where_open)

            if candidates.empty:
                print(f"Warning: No open SC for {symbol}")
                continue

            if not has_tranches:
                # Simple case - use the ID directly
                match = candidates[candidates["ID"] == id_val]
            else:
                # Complex case - match by expiration, strike, premium
                match = self._find_best_match(candidates, row)

            if match.empty:
                print(f"Warning: Could not find match for {snapshot_symbol}")
                continue

            self._close_trade_in_cagr(match, row)

        print("Finished closing expired short calls.")

    def _find_best_match(self, candidates: pd.DataFrame, snapshot_row: pd.Series) -> pd.DataFrame:
        """Match using priority: Expiration → Strike → Premium"""
        if candidates.empty:
            return candidates

        exp_date = snapshot_row['SC Exp Date']
        strike = snapshot_row['SC Strike Price']
        snapshot_premium = snapshot_row['SC Book Price']

        # 1. Expiration Date
        candidates = candidates[candidates['Exp Date'] == exp_date].copy()
        if candidates.empty:
            return candidates

        # 2. Strike Price
        candidates = candidates[candidates['Strike Price'] == strike].copy()
        if candidates.empty or len(candidates) == 1:
            return candidates

        # 3. Premium
        candidates = candidates.copy()
        candidates['parsed_premium'] = candidates['Entry Trade'].apply(self._parse_premium)
        candidates['premium_diff'] = (candidates['parsed_premium'] - snapshot_premium).abs()

        best_idx = candidates['premium_diff'].idxmin()
        return candidates.loc[[best_idx]] if best_idx is not None else pd.DataFrame()

    def _close_trade_in_cagr(self, match, row):
        pass

    @staticmethod
    def _parse_premium(entry_trade: str) -> float:
        """Extract premium from the Entry Trade column"""
        if not isinstance(entry_trade, str):
            return 0.0
        tokens = entry_trade.strip().split()
        for token in reversed(tokens):
            try:
                return float(token)
            except ValueError:
                continue
        return 0.0