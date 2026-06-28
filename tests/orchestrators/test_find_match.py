import pandas as pd
import pytest
from ebf_core.guards.guards import ContractError

from ebf_data.orchestrators.opex_processor import OpexProcessor


def make_opex_processor() -> OpexProcessor:
    """
    find_match only depends on self._parse_premium (a @staticmethod), so we
    bypass __init__ entirely - no CagrTable/SnapshotTable, no
    find_open_book, no real Excel touched.
    """
    return OpexProcessor.__new__(OpexProcessor)


def make_candidates(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def make_snapshot_row(exp_date: str, strike: float, premium: float) -> pd.Series:
    return pd.Series({
        "SC Exp Date": exp_date,
        "SC Strike Price": strike,
        "SC Book Price": premium,
    })


class TestFindMatch:
    """
    find_match is not a fuzzy/best-effort lookup: a matching open SC leg is
    always expected to exist. Every narrowing stage that comes up empty is
    therefore an error condition, not a normal "nothing found" outcome.
    """

    def test_empty_candidates_raises(self):
        sut = make_opex_processor()
        empty = make_candidates([])
        snapshot_row = make_snapshot_row("2026-06-19", 115.0, 1.75)

        with pytest.raises(ContractError, match="no candidates"):
            sut.find_match(empty, snapshot_row)

    def test_no_expiration_match_raises(self):
        sut = make_opex_processor()
        candidates = make_candidates([
            {"Exp Date": "2026-05-15", "Strike Price": 115.0, "Entry Trade": "STO 2 May-15 $115.00 C @ 1.75"},
        ])
        snapshot_row = make_snapshot_row("2026-06-19", 115.0, 1.75)

        with pytest.raises(ContractError, match="Exp Date"):
            sut.find_match(candidates, snapshot_row)

    def test_expiration_matches_but_no_strike_match_raises(self):
        sut = make_opex_processor()
        candidates = make_candidates([
            {"Exp Date": "2026-06-19", "Strike Price": 120.0, "Entry Trade": "STO 2 Jun-19 $120.00 C @ 1.75"},
        ])
        snapshot_row = make_snapshot_row("2026-06-19", 115.0, 1.75)

        with pytest.raises(ContractError, match="Strike Price"):
            sut.find_match(candidates, snapshot_row)

    def test_single_candidate_after_strike_filter_returned_without_parsing_premium(self):
        """When Exp Date + Strike narrow to exactly one row, that row is
        returned directly - premium parsing must never even run."""
        sut = make_opex_processor()
        candidates = make_candidates([
            {"Exp Date": "2026-06-19", "Strike Price": 115.0, "Entry Trade": "NOT A PARSEABLE STRING AT ALL"},
        ])
        snapshot_row = make_snapshot_row("2026-06-19", 115.0, 1.75)

        result = sut.find_match(candidates, snapshot_row)

        assert len(result) == 1
        assert result.iloc[0]["Strike Price"] == 115.0

    def test_multiple_candidates_disambiguated_by_closest_premium(self):
        """
        The documented scenario: same Symbol/ID, same Exp Date, same
        Strike Price, but two tranches opened at different premiums
        (received different premium at different times). The one
        closest to the snapshot's 'SC Book Price' must win.
        """
        sut = make_opex_processor()
        candidates = make_candidates([
            {"Exp Date": "2026-06-19", "Strike Price": 115.0, "Entry Trade": "STO 2 Jan-30 $115.00 C @ 1.75"},
            {"Exp Date": "2026-06-19", "Strike Price": 115.0, "Entry Trade": "STO 2 Feb-27 $115.00 C @ 10.76"},
        ])
        # snapshot premium is much closer to the second tranche's 10.76
        snapshot_row = make_snapshot_row("2026-06-19", 115.0, premium=10.50)

        result = sut.find_match(candidates, snapshot_row)

        assert len(result) == 1
        assert result.iloc[0]["Entry Trade"] == "STO 2 Feb-27 $115.00 C @ 10.76"

    def test_exact_premium_match_wins_with_zero_diff(self):
        sut = make_opex_processor()
        candidates = make_candidates([
            {"Exp Date": "2026-06-19", "Strike Price": 115.0, "Entry Trade": "STO 2 Jan-30 $115.00 C @ 1.75"},
            {"Exp Date": "2026-06-19", "Strike Price": 115.0, "Entry Trade": "STO 2 Feb-27 $115.00 C @ 10.76"},
        ])
        snapshot_row = make_snapshot_row("2026-06-19", 115.0, premium=1.75)

        result = sut.find_match(candidates, snapshot_row)

        assert len(result) == 1
        assert result.iloc[0]["Entry Trade"] == "STO 2 Jan-30 $115.00 C @ 1.75"

    def test_three_tranches_picks_nearest_of_all(self):
        sut = make_opex_processor()
        candidates = make_candidates([
            {"Exp Date": "2026-06-19", "Strike Price": 120.0, "Entry Trade": "STO 2 Apr-17 $120.00 C @ 10.27"},
            {"Exp Date": "2026-06-19", "Strike Price": 120.0, "Entry Trade": "STO 2 May-15 $120.00 C @ 8.93"},
            {"Exp Date": "2026-06-19", "Strike Price": 120.0, "Entry Trade": "STO 2 Jul-17 $120.00 C @ 10.36"},
        ])
        snapshot_row = make_snapshot_row("2026-06-19", 120.0, premium=10.30)

        result = sut.find_match(candidates, snapshot_row)

        assert len(result) == 1
        # 10.30 is nearest to 10.27 (diff 0.03) vs 10.36 (diff 0.06) vs 8.93 (diff 1.37)
        assert result.iloc[0]["Entry Trade"] == "STO 2 Apr-17 $120.00 C @ 10.27"

    def test_multi_candidate_result_carries_extra_working_columns(self):
        """
        Documents current behavior: the premium-disambiguation path leaves
        'parsed_premium' and 'premium_diff' bolted onto the returned row.
        This is NOT confirmed as correct/final - flagging via this test so
        it's visible and intentional if/when this gets cleaned up, rather
        than a silent surprise for whoever calls this next.
        """
        sut = make_opex_processor()
        candidates = make_candidates([
            {"Exp Date": "2026-06-19", "Strike Price": 115.0, "Entry Trade": "STO 2 Jan-30 $115.00 C @ 1.75"},
            {"Exp Date": "2026-06-19", "Strike Price": 115.0, "Entry Trade": "STO 2 Feb-27 $115.00 C @ 10.76"},
        ])
        snapshot_row = make_snapshot_row("2026-06-19", 115.0, premium=1.75)

        result = sut.find_match(candidates, snapshot_row)

        assert "parsed_premium" in result.columns
        assert "premium_diff" in result.columns