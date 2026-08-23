import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

import pytest

from ebf_data.sqlite import (
    SQLiteAccountRepository,
    SQLiteTradeCampaignRepository,
    connect_database,
    initialize_database,
)
from ebf_data.sqlite.database import transaction
from ebf_domain.money.money import Money
from ebf_trading.application import CreateTradeCampaign, FilledOptionTradeInput
from ebf_trading.domain.entities.account import Account
from ebf_trading.domain.entities.trade_campaign import TradeCampaign
from ebf_trading.domain.entities.trade_legs.trade_leg import TradeLeg
from ebf_trading.domain.value_objects.option_specific.option_type import OptionType
from ebf_trading.domain.value_objects.positions.position_side import PositionSide

ACCOUNT_ID = UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "journal.sqlite3"
    initialize_database(path)
    insert_account(path)
    return path


def insert_account(database: Path) -> None:
    account = Account(
        owner="Trade Owner",
        balance=Money.mint("10000"),
        id_value=ACCOUNT_ID,
    )
    with closing(connect_database(database)) as connection, transaction(connection):
        connection.execute(
            """
            INSERT INTO accounts (id, owner, balance_minor_units, balance_currency)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(account.id),
                account.owner,
                account.balance.amount_cents,
                account.balance.currency.iso_code,
            ),
        )


def trade_input() -> FilledOptionTradeInput:
    return FilledOptionTradeInput(
        ticker="xyz",
        option_type=OptionType.CALL,
        strike=Money.mint("50"),
        expiration=date(2026, 9, 18),
        side=PositionSide.LONG,
        contracts=2,
        fill_price=Money.mint("1.20"),
        fees=Money.mint("1.30"),
        fill_time=datetime(2026, 8, 21, 10, 30),
    )


def create_campaign(database: Path) -> tuple[TradeCampaign, TradeLeg]:
    operation = CreateTradeCampaign(
        SQLiteAccountRepository(database),
        SQLiteTradeCampaignRepository(database),
    )
    return operation.execute(ACCOUNT_ID, trade_input())


def test_allocate_reference_id_is_per_symbol_and_normalized(database: Path) -> None:
    repository = SQLiteTradeCampaignRepository(database)

    assert repository.allocate_reference_id(" xyz ") == "XYZ1"
    assert repository.allocate_reference_id("XYZ") == "XYZ2"
    assert repository.allocate_reference_id("abc") == "ABC1"


def test_allocate_reference_id_is_atomic_across_connections(database: Path) -> None:
    def allocate(_: int) -> str:
        return SQLiteTradeCampaignRepository(database).allocate_reference_id("XYZ")

    with ThreadPoolExecutor(max_workers=8) as executor:
        references = list(executor.map(allocate, range(24)))

    assert len(set(references)) == 24
    assert {int(reference.removeprefix("XYZ")) for reference in references} == set(range(1, 25))


def test_add_persists_the_initial_creation_aggregate(database: Path) -> None:
    campaign, leg = create_campaign(database)

    with closing(connect_database(database)) as connection:
        campaign_row = connection.execute("SELECT * FROM trade_campaigns").fetchone()
        leg_row = connection.execute("SELECT * FROM trade_legs").fetchone()
        order_row = connection.execute("SELECT * FROM orders").fetchone()
        event_row = connection.execute("SELECT * FROM transaction_events").fetchone()

    assert dict(campaign_row) == {
        "id": str(campaign.id),
        "account_id": str(ACCOUNT_ID),
        "ticker": "XYZ",
        "reference_number": 1,
        "reference_id": "XYZ1",
    }
    assert dict(leg_row) == {
        "id": str(leg.id),
        "campaign_id": str(campaign.id),
        "option_type": "call",
        "strike_minor_units": 5_000,
        "strike_currency": "USD",
        "expiration_at": "2026-09-18T16:00:00-04:00",
        "position_side": "long",
        "contract_quantity": 2,
    }
    assert dict(order_row) == {
        "id": 1,
        "campaign_id": str(campaign.id),
        "leg_id": str(leg.id),
        "submission_at": "2026-08-21T10:30:00-04:00",
        "order_spec_type": "market",
        "fill_at": "2026-08-21T10:30:00-04:00",
        "fill_price_minor_units": 120,
        "fill_price_currency": "USD",
        "fees_minor_units": 130,
        "fees_currency": "USD",
        "contract_quantity": 2,
    }
    assert dict(event_row) == {
        "id": str(campaign.events[0].id),
        "campaign_id": str(campaign.id),
        "leg_id": str(leg.id),
        "order_id": 1,
        "event_type": "open",
        "notes": None,
    }


def test_add_rolls_back_every_aggregate_row_when_event_insert_fails(database: Path) -> None:
    with closing(connect_database(database)) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_transaction_event
            BEFORE INSERT ON transaction_events
            BEGIN
                SELECT RAISE(ABORT, 'event insert rejected');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="event insert rejected"):
        create_campaign(database)

    with closing(connect_database(database)) as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("trade_campaigns", "trade_legs", "orders", "transaction_events")
        }

    assert counts == {
        "trade_campaigns": 0,
        "trade_legs": 0,
        "orders": 0,
        "transaction_events": 0,
    }
