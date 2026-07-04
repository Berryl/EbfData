import pandas as pd
from ebf_core.guards import guards as g
from ebf_core.guards.guards import ContractError
from ebf_trading.domain.date_time.market_days import market_close_datetime
from ebf_trading.domain.entities.transaction_events.transaction_event_type import TransactionEventType

from ebf_data.excel.cagr.cagr_table import CagrTable
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable
from ebf_data.excel.orchestrators.symbol_translator import SymbolTranslator


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

        for snapshot_index, row in to_close.iterrows():
            snapshot_symbol = row['Symbol']
            symbol, id_val, has_tranches = self._symbol_translator.to_cagr_values(snapshot_symbol)

            # Get open SC trades in CAGR for this symbol
            candidates = self._cagr.get_trade(symbol, id_val)
            candidates = self._cagr.by_position(candidates, "SC").pipe(self._cagr.where_open)

            if candidates.empty:
                print(f"Warning: No open SC for {symbol}")
                continue

            try:
                if not has_tranches:
                    # Simple case - use the ID directly
                    match = candidates[candidates["ID"] == id_val]
                    g.ensure_true(not match.empty, f"No open SC leg found with ID={id_val}")
                else:
                    # Complex case - match by expiration, strike, premium
                    match = self.find_match(candidates, row)
            except ContractError as e:
                print(f"Warning: Could not find match for {snapshot_symbol} - {e}")
                continue

            self._close_trade_in_cagr(match, row, TransactionEventType.EXPIRATION)
            self._snapshot.clear_short_call_columns(snapshot_index)

        print("Finished closing expired short calls.")

    def find_match(self, candidates: pd.DataFrame, snapshot_row: pd.Series) -> pd.DataFrame:
        """
        Find the exact open SC leg this snapshot row corresponds to.

        Narrows by Expiration Date -> Strike Price -> Premium (only as a
        tiebreaker between tranches at the same Exp Date/Strike). This is
        not a fuzzy/best-effort match: a match is always expected to exist.
        Failing to find one is an error, not a normal outcome.

        Raises:
            ContractError: if no candidate survives any narrowing stage.
        """
        g.ensure_true(not candidates.empty, "find_match received no candidates to match against")

        exp_date = snapshot_row['SC Exp Date']
        strike = snapshot_row['SC Strike Price']
        snapshot_premium = snapshot_row['SC Book Price']

        # 1. Expiration Date
        candidates = candidates[candidates['Exp Date'] == exp_date].copy()
        g.ensure_true(not candidates.empty, f"No open SC leg found with Exp Date={exp_date!r}")

        # 2. Strike Price
        candidates = candidates[candidates['Strike Price'] == strike].copy()
        g.ensure_true(not candidates.empty, f"No open SC leg found with Strike Price={strike!r}")
        if len(candidates) == 1:
            return candidates

        # 3. Premium - tiebreaker only used when multiple tranches share the same Exp Date and Strike Price.
        candidates = candidates.copy()
        candidates['parsed_premium'] = candidates['Entry Trade'].apply(self._parse_premium)
        candidates['premium_diff'] = (candidates['parsed_premium'] - snapshot_premium).abs()

        best_idx = candidates['premium_diff'].idxmin()
        return candidates.loc[[best_idx]]

    def _close_trade_in_cagr(self, match: pd.DataFrame, row: pd.Series, event: TransactionEventType) -> None:
        underlying_price = row['Last Price']
        exit_fill_time = market_close_datetime(row['SC Exp Date'])
        self._cagr.close_trade_leg(match, event, underlying_price, exit_fill_time)

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