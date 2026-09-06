"""Tests for the SQLite journal selector read model."""

from pathlib import Path
from uuid import UUID

import pytest
from ebf_domain.money.money import Money
from ebf_trading.application.queries import CampaignChoices, CampaignQuery, CampaignStatusFilter
from ebf_trading.domain.entities.account import Account

from ebf_data.sqlite import SQLiteJournalCampaignQuery, initialize_database
from tests.sqlite.support import insert_account, insert_query_campaign


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "journal.sqlite3"
    initialize_database(path)
    acct = Account(owner="Journal Owner", balance=Money.mint("10000"), id_value=UUID(int=1))
    insert_account(path, acct)

    insert_query_campaign(path, acct_id=acct.id, ticker="MARA", ref_number=1, leg_states=("closed", "open"))
    insert_query_campaign(path, acct_id=acct.id, ticker="FCX", ref_number=10, leg_states=("open",))
    insert_query_campaign(path, acct_id=acct.id, ticker="AAPL", ref_number=1, leg_states=("closed", "closed"))
    insert_query_campaign(path, acct_id=acct.id, ticker="DRAM", ref_number=1, leg_states=("open",))
    insert_query_campaign(path, acct_id=acct.id, ticker="FCX", ref_number=2, leg_states=("open",))
    insert_query_campaign(path, acct_id=acct.id, ticker="FCX", ref_number=1, leg_states=("closed",))
    return path


class TestSQLiteJournalCampaignQuery:
    @pytest.fixture
    def sut(self, db: Path) -> CampaignQuery:
        return SQLiteJournalCampaignQuery(db)

    class TestSymbols:
        def test_symbols_are_sorted_alphabetically(self, sut: CampaignQuery) -> None:
            assert sut.list_symbols(CampaignStatusFilter.ACTIVE) == ("DRAM", "FCX", "MARA")
            assert sut.list_symbols(CampaignStatusFilter.CLOSED) == ("AAPL", "FCX")
            assert sut.list_symbols(CampaignStatusFilter.ALL) == ("AAPL", "DRAM", "FCX", "MARA")

        def test_default_status_is_active(self, sut: CampaignQuery) -> None:
            assert sut.list_symbols() == sut.list_symbols(CampaignStatusFilter.ACTIVE)

    class TestCampaigns:
        def test_campaigns_are_sorted_in_numeric_order(self, sut: CampaignQuery) -> None:
            refs = [c.reference_id for c in sut.list_campaigns("FCX", CampaignStatusFilter.ALL).campaigns]
            assert refs == ["FCX1", "FCX2", "FCX10"]

        def test_list_campaigns_active_numeric_order(self, sut: CampaignQuery) -> None:
            refs = [c.reference_id for c in sut.list_campaigns("FCX").campaigns]
            assert refs == ["FCX2", "FCX10"]

        def test_can_filter_by_closed_only(self, sut: CampaignQuery) -> None:
            refs = [c.reference_id for c in sut.list_campaigns("FCX", CampaignStatusFilter.CLOSED).campaigns]
            assert refs == ["FCX1"]

        def test_symbol_is_normalized(self, sut: CampaignQuery) -> None:
            refs = [c.reference_id for c in sut.list_campaigns(" fcx ").campaigns]
            assert refs == ["FCX2", "FCX10"] # normalized = trimmed_and_upper_cased

        def test_missing_symbol_raises(self, sut: CampaignQuery) -> None:
            with pytest.raises(ValueError):
                sut.list_campaigns("  ")

    class TestStatusFromLegs:
        def test_any_open_leg_makes_campaign_active(self, sut: CampaignQuery) -> None:
            assert [c.reference_id for c in sut.list_campaigns("DRAM").campaigns] == ["DRAM1"]
            assert [c.reference_id for c in sut.list_campaigns("DRAM", CampaignStatusFilter.CLOSED).campaigns] == []
            assert [c.reference_id for c in sut.list_campaigns("MARA").campaigns] == ["MARA1"]
            assert [c.reference_id for c in sut.list_campaigns("MARA", CampaignStatusFilter.CLOSED).campaigns] == []

        def test_all_legs_closed_makes_campaign_closed(self, sut: CampaignQuery) -> None:
            assert [c.reference_id for c in sut.list_campaigns("AAPL").campaigns] == []
            assert [c.reference_id for c in sut.list_campaigns("AAPL", CampaignStatusFilter.CLOSED).campaigns] == [
                "AAPL1"
            ]

    class TestWhenUnknownSymbol:
        @pytest.mark.parametrize("status", list(CampaignStatusFilter))
        def test_returns_empty_choices(self, sut: CampaignQuery, status: CampaignStatusFilter) -> None:
            assert sut.list_campaigns("MISSING", status) == CampaignChoices(())
