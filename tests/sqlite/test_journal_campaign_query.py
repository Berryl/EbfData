"""Tests for the SQLite journal selector read model."""

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from ebf_trading.application.queries import CampaignChoices, CampaignQuery, CampaignStatusFilter

from ebf_data.sqlite import SQLiteJournalCampaignQuery, connect_database, initialize_database
from ebf_data.sqlite.database import transaction

CLOSED_AT = "2026-08-22T15:00:00-04:00"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "journal.sqlite3"
    initialize_database(path)
    conn = connect_database(path)
    try:
        with transaction(conn):
            conn.execute(
                """
                INSERT INTO accounts (id, owner, balance_minor_units, balance_currency)
                VALUES (?, ?, ?, ?)
                """,
                (str(UUID(int=1)), "Journal Owner", 1_000_000, "USD"),
            )
            _insert_campaign(conn, "MIX", 1, (CLOSED_AT, None))
            _insert_campaign(conn, "FCX", 10, (None,))
            _insert_campaign(conn, "AAPL", 1, (CLOSED_AT, CLOSED_AT))
            _insert_campaign(conn, "DRAM", 1, (None,))
            _insert_campaign(conn, "FCX", 2, (None,))
            _insert_campaign(conn, "FCX", 1, (CLOSED_AT,))
    finally:
        conn.close()
    return path


def _insert_campaign(
        conn: sqlite3.Connection, ticker: str, ref_number: int, leg_exit_times: Iterable[str | None],
) -> None:
    campaign_id = str(uuid4())
    conn.execute(
        """
        INSERT INTO trade_campaigns (id, account_id, ticker, reference_number, reference_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            campaign_id,
            str(UUID(int=1)),
            ticker,
            ref_number,
            f"{ticker}{ref_number}",
        ),
    )
    for exit_at in leg_exit_times:
        conn.execute(
            """
            INSERT INTO trade_legs (id, campaign_id, option_type, strike_minor_units,
                                    strike_currency, expiration_at, position_side,
                                    contract_quantity, exit_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                campaign_id,
                "call",
                5_000,
                "USD",
                "2026-09-18T16:00:00-04:00",
                "long",
                1,
                exit_at,
            ),
        )


def _references(choices: CampaignChoices) -> tuple[str, ...]:
    return tuple(choice.reference_id for choice in choices.campaigns)


def test_status_classification_uses_leg_exit_at(db: Path) -> None:
    qry = SQLiteJournalCampaignQuery(db)

    assert _references(qry.list_campaigns("DRAM")) == ("DRAM1",)
    assert _references(qry.list_campaigns("DRAM", CampaignStatusFilter.CLOSED)) == ()
    assert _references(qry.list_campaigns("AAPL")) == ()
    assert _references(qry.list_campaigns("AAPL", CampaignStatusFilter.CLOSED)) == ("AAPL1",)
    assert _references(qry.list_campaigns("MIX")) == ("MIX1",)
    assert _references(qry.list_campaigns("MIX", CampaignStatusFilter.CLOSED)) == ()


def test_status_filters_symbols_and_sorts_them_alphabetically(db: Path) -> None:
    qry = SQLiteJournalCampaignQuery(db)

    assert qry.list_symbols(CampaignStatusFilter.ACTIVE) == ("DRAM", "FCX", "MIX")
    assert qry.list_symbols(CampaignStatusFilter.CLOSED) == ("AAPL", "FCX")
    assert qry.list_symbols(CampaignStatusFilter.ALL) == ("AAPL", "DRAM", "FCX", "MIX")


def test_status_filters_default_is_active_status(db: Path) -> None:
    qry: CampaignQuery = SQLiteJournalCampaignQuery(db)
    assert qry.list_symbols() == qry.list_symbols(CampaignStatusFilter.ACTIVE)
    assert qry.list_campaigns("FCX") == qry.list_campaigns("FCX", CampaignStatusFilter.ACTIVE)


def test_campaigns_are_filtered_and_sorted_by_numeric_reference(db: Path) -> None:
    query = SQLiteJournalCampaignQuery(db)

    assert _references(query.list_campaigns(" fcx ")) == ("FCX2", "FCX10")
    assert _references(query.list_campaigns("FCX", CampaignStatusFilter.CLOSED)) == ("FCX1",)
    assert _references(query.list_campaigns("FCX", CampaignStatusFilter.ALL)) == ("FCX1", "FCX2", "FCX10",)


@pytest.mark.parametrize("status", list(CampaignStatusFilter))
def test_missing_symbol_returns_empty_choices(db: Path, status: CampaignStatusFilter) -> None:
    query = SQLiteJournalCampaignQuery(db)

    assert query.list_campaigns("MISSING", status) == CampaignChoices(())
