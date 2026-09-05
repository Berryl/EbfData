"""Tests for the SQLite journal selector read model."""

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from ebf_data.sqlite import SQLiteJournalCampaignQuery, connect_database, initialize_database
from ebf_data.sqlite.database import transaction
from ebf_trading.application.queries import CampaignStatusFilter, JournalCampaignChoices

CLOSED_AT = "2026-08-22T15:00:00-04:00"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "journal.sqlite3"
    initialize_database(path)
    connection = connect_database(path)
    try:
        with transaction(connection):
            connection.execute(
                """
                INSERT INTO accounts (id, owner, balance_minor_units, balance_currency)
                VALUES (?, ?, ?, ?)
                """,
                (str(UUID(int=1)), "Journal Owner", 1_000_000, "USD"),
            )
            _insert_campaign(connection, "MIX", 1, (CLOSED_AT, None))
            _insert_campaign(connection, "FCX", 10, (None,))
            _insert_campaign(connection, "AAPL", 1, (CLOSED_AT, CLOSED_AT))
            _insert_campaign(connection, "DRAM", 1, (None,))
            _insert_campaign(connection, "FCX", 2, (None,))
            _insert_campaign(connection, "FCX", 1, (CLOSED_AT,))
    finally:
        connection.close()
    return path


def _insert_campaign(
        conn: sqlite3.Connection,ticker: str,ref_number: int,leg_exit_times: Iterable[str | None],
) -> None:
    campaign_id = str(uuid4())
    conn.execute(
        """
        INSERT INTO trade_campaigns (
            id, account_id, ticker, reference_number, reference_id
        ) VALUES (?, ?, ?, ?, ?)
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
            INSERT INTO trade_legs (
                id, campaign_id, option_type, strike_minor_units,
                strike_currency, expiration_at, position_side,
                contract_quantity, exit_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def _references(choices: JournalCampaignChoices) -> tuple[str, ...]:
    return tuple(choice.reference_id for choice in choices.campaigns)


def test_status_classification_uses_leg_exit_at(db: Path) -> None:
    query = SQLiteJournalCampaignQuery(db)

    assert _references(query.list_campaigns("DRAM")) == ("DRAM1",)
    assert _references(query.list_campaigns("DRAM", CampaignStatusFilter.CLOSED)) == ()
    assert _references(query.list_campaigns("AAPL")) == ()
    assert _references(query.list_campaigns("AAPL", CampaignStatusFilter.CLOSED)) == (
        "AAPL1",
    )
    assert _references(query.list_campaigns("MIX")) == ("MIX1",)
    assert _references(query.list_campaigns("MIX", CampaignStatusFilter.CLOSED)) == ()


def test_status_filters_symbols_and_sorts_them_alphabetically(db: Path) -> None:
    query = SQLiteJournalCampaignQuery(db)

    assert query.list_symbols() == ("DRAM", "FCX", "MIX")
    assert query.list_symbols(CampaignStatusFilter.CLOSED) == ("AAPL", "FCX")
    assert query.list_symbols(CampaignStatusFilter.ALL) == ("AAPL", "DRAM", "FCX", "MIX")


def test_campaigns_are_filtered_and_sorted_by_numeric_reference(db: Path) -> None:
    query = SQLiteJournalCampaignQuery(db)

    assert _references(query.list_campaigns(" fcx ")) == ("FCX2", "FCX10")
    assert _references(query.list_campaigns("FCX", CampaignStatusFilter.CLOSED)) == ("FCX1",)
    assert _references(query.list_campaigns("FCX", CampaignStatusFilter.ALL)) == (
        "FCX1",
        "FCX2",
        "FCX10",
    )


def test_include_all_depends_on_the_filtered_campaign_count(db: Path) -> None:
    query = SQLiteJournalCampaignQuery(db)

    assert query.list_campaigns("MISSING").include_all is False
    assert query.list_campaigns("DRAM").include_all is False
    assert query.list_campaigns("FCX", CampaignStatusFilter.CLOSED).include_all is False
    assert query.list_campaigns("FCX").include_all is True
    assert query.list_campaigns("FCX", CampaignStatusFilter.ALL).include_all is True
