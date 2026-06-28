from ebf_data.excel.cagr.cagr_table import CagrTable
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable
from ebf_core.guards import guards as g


class OpexProcessor:
    def __init__(self, cagr: CagrTable, snapshot: SnapshotTable) -> None:
        g.ensure_not_none(cagr, "cagr")
        g.ensure_not_none(snapshot, "snapshot")

        self._cagr = cagr
        self._snapshot = snapshot

    def close_out_expired_short_calls(self) -> None:
        to_close = self._snapshot.get_expired_short_calls()

        ## find the matching trade legs in CAGR
        ## --> use the symbol translator to find the matching symbol
        ## --> if multiple tranches match on strike, then by premium if necessary
        ## --> close the short call in CAGR (“Is Closed” = ‘Y’, “Exit Trigger” = ‘OPEX’,
        #                                       “Exit Fill Time” = OPEX closing time, “Exit Trade” = "Expiration
        ## ---> Clear snapshot columns
        # (SC Exp Date, SC Strike Price, SC Qty, SC Book Date, SC Fill Date, SC Book Price,
        # SC Fill Delta, SC Current Ask , SC Current Delta, SC Buy Back Cutoff
