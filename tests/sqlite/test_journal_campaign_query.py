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

        class TestSymbolNormalization:
            """Symbol input is normalized and validated consistently."""

            def test_symbol_is_normalized(self, sut: CampaignQuery) -> None:
                refs = [c.reference_id for c in sut.list_campaigns(" fcx ").campaigns]
                assert refs == ["FCX2", "FCX10"]

    class TestStatusFromLegs:

        def test_all_legs_closed_makes_campaign_closed(self, sut: CampaignQuery) -> None:
            ticker = 'AAPL'
            closed_campaigns = sut.list_campaigns(ticker, CampaignStatusFilter.CLOSED).campaigns
            active_campaigns = sut.list_campaigns(ticker).campaigns

            assert [c.reference_id for c in closed_campaigns] == ["AAPL1"]
            assert [c.reference_id for c in active_campaigns] == []

        @pytest.mark.parametrize("ticker, ref_id", [('DRAM', 'DRAM1'), ('MARA', 'MARA1')])
        def test_any_open_leg_makes_campaign_active(self, sut: CampaignQuery, ticker, ref_id) -> None:
            closed_campaigns = sut.list_campaigns(ticker, CampaignStatusFilter.CLOSED).campaigns
            active_campaigns = sut.list_campaigns(ticker).campaigns

            assert [c.reference_id for c in closed_campaigns] == []
            assert [c.reference_id for c in active_campaigns] == [ref_id]

    class TestWhenUnknownSymbol:
        @pytest.mark.parametrize("status", list(CampaignStatusFilter))
        def test_returns_empty_choices(self, sut: CampaignQuery, status: CampaignStatusFilter) -> None:
            assert sut.list_campaigns("MISSING", status) == CampaignChoices(())
