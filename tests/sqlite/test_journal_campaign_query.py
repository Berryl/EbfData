"""Tests for the SQLite journal selector read model."""

from pathlib import Path
from uuid import UUID

import pytest

from ebf_data.sqlite import SQLiteJournalCampaignQuery, initialize_database
from ebf_domain.money.money import Money
from ebf_trading.application.queries import CampaignChoices, CampaignQuery, CampaignStatusFilter
from ebf_trading.domain.entities.account import Account
from tests.sqlite.support import insert_account, insert_query_campaign


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "journal.sqlite3"
    initialize_database(path)
    account = Account(owner="Journal Owner", balance=Money.mint("10000"), id_value=UUID(int=1))
    insert_account(path, account)
    insert_query_campaign(path, account_id=account.id, ticker="MARA", reference_number=1, leg_states=("closed", "open"))
    insert_query_campaign(path, account_id=account.id, ticker="FCX", reference_number=10, leg_states=("open",))
    insert_query_campaign(
        path, account_id=account.id, ticker="AAPL", reference_number=1, leg_states=("closed", "closed")
    )
    insert_query_campaign(path, account_id=account.id, ticker="DRAM", reference_number=1, leg_states=("open",))
    insert_query_campaign(path, account_id=account.id, ticker="FCX", reference_number=2, leg_states=("open",))
    insert_query_campaign(path, account_id=account.id, ticker="FCX", reference_number=1, leg_states=("closed",))
    return path


def _get_ref_ids(choices: CampaignChoices) -> tuple[str, ...]:
    return tuple(choice.reference_id for choice in choices.campaigns)


def test_status_classification_uses_leg_exit_at(db: Path) -> None:
    qry = SQLiteJournalCampaignQuery(db)

    assert _get_ref_ids(qry.list_campaigns("DRAM")) == ("DRAM1",)
    assert _get_ref_ids(qry.list_campaigns("DRAM", CampaignStatusFilter.CLOSED)) == ()
    assert _get_ref_ids(qry.list_campaigns("AAPL")) == ()
    assert _get_ref_ids(qry.list_campaigns("AAPL", CampaignStatusFilter.CLOSED)) == ("AAPL1",)
    assert _get_ref_ids(qry.list_campaigns("MARA")) == ("MARA1",)
    assert _get_ref_ids(qry.list_campaigns("MARA", CampaignStatusFilter.CLOSED)) == ()


def test_status_filters_symbols_and_sorts_them_alphabetically(db: Path) -> None:
    qry = SQLiteJournalCampaignQuery(db)

    assert qry.list_symbols(CampaignStatusFilter.ACTIVE) == ("DRAM", "FCX", "MARA")
    assert qry.list_symbols(CampaignStatusFilter.CLOSED) == ("AAPL", "FCX")
    assert qry.list_symbols(CampaignStatusFilter.ALL) == ("AAPL", "DRAM", "FCX", "MARA")


def test_status_filters_default_is_active_status(db: Path) -> None:
    qry: CampaignQuery = SQLiteJournalCampaignQuery(db)
    assert qry.list_symbols() == qry.list_symbols(CampaignStatusFilter.ACTIVE)
    assert qry.list_campaigns("FCX") == qry.list_campaigns("FCX", CampaignStatusFilter.ACTIVE)


def test_campaigns_are_filtered_and_sorted_by_numeric_reference(db: Path) -> None:
    query = SQLiteJournalCampaignQuery(db)

    assert _get_ref_ids(query.list_campaigns(" fcx ")) == ("FCX2", "FCX10")
    assert _get_ref_ids(query.list_campaigns("FCX", CampaignStatusFilter.CLOSED)) == ("FCX1",)
    assert _get_ref_ids(query.list_campaigns("FCX", CampaignStatusFilter.ALL)) == (
        "FCX1",
        "FCX2",
        "FCX10",
    )


@pytest.mark.parametrize("status", list(CampaignStatusFilter))
def test_missing_symbol_returns_empty_choices(db: Path, status: CampaignStatusFilter) -> None:
    query = SQLiteJournalCampaignQuery(db)

    assert query.list_campaigns("MISSING", status) == CampaignChoices(())
